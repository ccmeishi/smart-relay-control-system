"""温湿度感应器模拟器

功能(对应任务要求):
  1. Modbus TCP 采集: 从 config.json 指定的从站(192.168.20.59:5502)周期读取
     保持寄存器 0x0000~0x0009(功能码 0x03)
  2. JSON 存储: 采集值保存在 sensor_data.json, 作为"上一次的值"
  3. 变化上报: 值发生变化时立即更新 JSON 并把 payload 发布到 MQTT
     (172.16.4.211:9783, 账号 test/123456), 保留消息(retain), 断线自动重连
  4. 心跳: 数据无变化时每 60 秒发一次心跳, 证明设备在线
  5. 遗嘱(LWT): 异常掉线时 broker 自动发布 offline, 正常上线发布 online
  6. 写寄存器: 订阅命令主题, 收到 {"cmd":"write","register":偏移,"value":整数}
     时用功能码 0x06 写入本组寄存器, 并回 write_ack(呼应"可读可写"要求)

上报 topic : device/sensor/sevengroup      (数据/心跳/在线状态)
命令 topic : device/sensor/sevengroup/cmd  (read / query / write)

运行: python sensor_simulator.py
依赖: pip install pymodbus==3.6.9 paho-mqtt==1.6.1
"""

import json
import logging
import queue
import time
from datetime import datetime

import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient

CONFIG_PATH = "config.json"
DATA_PATH = "sensor_data.json"
HEARTBEAT_S = 60      # 心跳周期: 数据无变化时也要定时证明在线
RECONNECT_S = 5       # Modbus 断线后的重连间隔
TICK_S = 0.2          # 主循环节拍

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("sensor")

DEFAULT_CONFIG = {
    "modbus": {
        "host": "192.168.20.59", "port": 5502, "unit_id": 1,
        "register_start": 0, "register_count": 10, "poll_interval": 5
    },
    "mqtt": {
        "host": "172.16.4.211", "port": 9783,
        "username": "test", "password": "123456",
        "client_id": "sensor_sevengroup",
        "topic_data": "device/sensor/sevengroup",
        "topic_cmd": "device/sensor/sevengroup/cmd"
    },
    # 寄存器含义映射: 相对偏移 -> 名称/缩放/是否按有符号解释; 未映射的按原始值上报
    "register_map": {
        "0": {"name": "temperature", "scale": 0.1, "signed": True, "unit": "C"},
        "1": {"name": "humidity", "scale": 0.1, "signed": False, "unit": "%RH"}
    }
}

wq = queue.Queue()          # MQTT 回调线程 -> 主循环 的命令队列(避免跨线程操作 Modbus)
mqtt_client = None
device_id = "sensor01"
topic_data = topic_cmd = ""
reg_base = 0                # 寄存器起始地址(终端显示用)


def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, obj):
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)
    except OSError as e:
        log.error("保存 %s 失败: %s", path, e)


def now_s():
    return datetime.now().isoformat(timespec="seconds")


def to_signed(raw):
    """16 位寄存器按有符号数解释(温度可能出现负值)"""
    return raw - 65536 if raw > 32767 else raw


def parse_values(regs, register_map):
    """把原始寄存器按 register_map 解析成带名字的物理量"""
    values = {}
    for idx, spec in register_map.items():
        i = int(idx)
        if i >= len(regs):
            continue
        raw = to_signed(regs[i]) if spec.get("signed") else regs[i]
        values[spec["name"]] = round(raw * spec.get("scale", 1), 2)
    return values


def brief_line(p):
    """把上报 payload 压缩成一行终端摘要(MQTT 报文本身不变)"""
    t = p.get("type")
    if t == "data":
        parts = ["数据"]
        if "temperature" in p:
            parts.append("温度 %s°C" % p["temperature"])
        if "humidity" in p:
            parts.append("湿度 %s%%RH" % p["humidity"])
        if "temperature" not in p and p.get("registers") is not None:
            parts.append("寄存器 " + str(p["registers"]).replace(" ", ""))
        return "  ".join(parts)
    if t == "heartbeat":
        return "心跳  在线 %ss" % p.get("uptime")
    if t == "online":
        return "上线"
    if t == "write_ack":
        return "写入  寄存器0x%04X = %s  成功" % (reg_base + int(p.get("register", 0)), p.get("value"))
    if t == "error":
        return "错误  %s" % p.get("detail")
    return str(t)


def publish(payload, retain=False, qos=1):
    """统一上报入口: 自动补 deviceId/ts, 终端打印一行摘要"""
    payload = dict(payload)
    payload.setdefault("deviceId", device_id)
    payload["ts"] = now_s()
    text = json.dumps(payload, ensure_ascii=False)
    try:
        info = mqtt_client.publish(topic_data, text, retain=retain, qos=qos)
        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            log.info(brief_line(payload))
        else:
            log.warning("发布未成功(rc=%s): %s", info.rc, brief_line(payload))
    except (OSError, RuntimeError) as e:
        log.warning("MQTT 发布异常: %s", e)


def on_connect(client, _userdata, _flags, rc):
    log.info("MQTT 已连接")
    client.subscribe(topic_cmd, qos=1)
    publish({"type": "online"}, retain=True)
    wq.put(("read",))                    # 重连后立即采集一次, 补报当前状态


def on_disconnect(_client, _userdata, rc):
    log.warning("MQTT 断开, 自动重连中")


def on_cmd(_client, _userdata, msg):
    """paho 线程中执行: 只解析并入队, 由主循环实际操作 Modbus"""
    text = msg.payload.decode("utf-8", "replace")
    try:
        cmd = json.loads(text)
    except ValueError:
        publish({"type": "error", "detail": "bad json: %s" % text[:80]})
        return
    action = cmd.get("cmd")
    if action == "write":
        reg, val = cmd.get("register"), cmd.get("value")
        if isinstance(reg, int) and isinstance(val, int) and not isinstance(reg, bool):
            wq.put(("write", reg, val))
        else:
            publish({"type": "error", "detail": "write 需要 integer 的 register/value"})
    elif action == "read":
        wq.put(("read",))
    elif action == "query":
        wq.put(("query",))
    else:
        publish({"type": "error", "detail": "未知命令, 支持 read/query/write"})


def modbus_connect(mb_cfg):
    client = ModbusTcpClient(mb_cfg["host"], port=int(mb_cfg["port"]))
    if client.connect():
        log.info("Modbus 已连接")
        return client
    log.warning("Modbus 连接失败 %s:%s, %ds 后重试", mb_cfg["host"], mb_cfg["port"], RECONNECT_S)
    return None


def main():
    global mqtt_client, device_id, topic_data, topic_cmd, reg_base

    cfg = load_json(CONFIG_PATH, DEFAULT_CONFIG)
    mb_cfg, mq_cfg = cfg["modbus"], cfg["mqtt"]
    reg_map = cfg.get("register_map", {})
    reg_start = int(mb_cfg["register_start"])
    reg_count = int(mb_cfg["register_count"])
    unit_id = int(mb_cfg.get("unit_id", 1))
    poll_s = float(mb_cfg.get("poll_interval", 5))

    device_id = mq_cfg.get("client_id", "sensor01")
    topic_data = mq_cfg["topic_data"]
    topic_cmd = mq_cfg["topic_cmd"]
    reg_base = reg_start

    store = load_json(DATA_PATH, {"registers": None, "values": None, "last_change": None})

    # ---- MQTT: 异步连接 + 自动重连 + 遗嘱 ----
    mqtt_client = mqtt.Client(client_id=device_id, clean_session=True)
    if mq_cfg.get("username"):
        mqtt_client.username_pw_set(mq_cfg["username"], mq_cfg.get("password"))
    will = json.dumps({"deviceId": device_id, "type": "offline"}, ensure_ascii=False)
    mqtt_client.will_set(topic_data, will, qos=1, retain=True)
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_cmd
    mqtt_client.reconnect_delay_set(min_delay=5, max_delay=60)
    mqtt_client.connect_async(mq_cfg["host"], int(mq_cfg["port"]), keepalive=60)
    mqtt_client.loop_start()

    # ---- 主循环 ----
    mb = None
    next_poll = 0.0                       # 启动即先采集一次
    next_hb = time.time() + HEARTBEAT_S
    last_retry = 0.0
    start_time = time.time()
    log.info("模拟器启动 | Modbus %s:%s 寄存器 0x%04X~0x%04X 每%gs轮询 | MQTT %s:%s | 上报主题 %s",
             mb_cfg["host"], mb_cfg["port"], reg_start, reg_start + reg_count - 1, poll_s,
             mq_cfg["host"], mq_cfg["port"], topic_data)

    try:
        while True:
            now = time.time()

            read_force_pub = False   # 标记: read 命令触发的立即采集, 无论变没变都强制发布

            # 1) 处理 MQTT 下发的命令
            while not wq.empty():
                job = wq.get()
                if job[0] == "write":
                    _, offset, value = job
                    if not 0 <= offset < reg_count:     # 只允许写本组寄存器, 避免误写其他组的
                        publish({"type": "error",
                                 "detail": "寄存器偏移 %s 超出本组范围 0x%04X~0x%04X, 已拒绝写入"
                                           % (offset, reg_start, reg_start + reg_count - 1)})
                    else:
                        addr = reg_start + offset
                        if mb is None and now - last_retry >= RECONNECT_S:
                            last_retry = now
                            mb = modbus_connect(mb_cfg)
                        if mb is None:
                            publish({"type": "error", "detail": "Modbus 未连接, 写入失败"})
                        else:
                            try:
                                rr = mb.write_register(addr, value, slave=unit_id)
                                if rr.isError():
                                    publish({"type": "error", "detail": "写寄存器失败: %s" % rr})
                                else:
                                    publish({"type": "write_ack", "register": offset, "value": value})
                                    next_poll = 0          # 写入后立即重新采集
                            except Exception as e:
                                log.warning("Modbus 写失败: %s", e)
                                mb.close()
                                mb = None
                elif job[0] == "read":
                    read_force_pub = True             # 标记强制发布
                    next_poll = 0                      # 触发立即采集
                elif job[0] == "query":
                    if store.get("registers") is not None:
                        publish({"type": "data", **(store.get("values") or {}),
                                 "registers": store["registers"]})

            # 2) 周期采集
            if now >= next_poll:
                next_poll = now + poll_s
                if mb is None and now - last_retry >= RECONNECT_S:
                    last_retry = now
                    mb = modbus_connect(mb_cfg)
                if mb is not None:
                    try:
                        rr = mb.read_holding_registers(reg_start, count=reg_count, slave=unit_id)
                        if rr.isError():
                            raise RuntimeError(str(rr))
                        regs = list(rr.registers)
                        if regs != store.get("registers") or read_force_pub:
                            values = parse_values(regs, reg_map)
                            store["registers"] = regs
                            store["values"] = values
                            store["last_change"] = now_s()
                            save_json(DATA_PATH, store)
                            publish({"type": "data", **values, "registers": regs}, retain=True)
                        # 无变化且非强制: 不上报, 等心跳兜底
                    except Exception as e:
                        log.warning("Modbus 读取失败: %s", e)
                        try:
                            mb.close()
                        except Exception:
                            pass
                        mb = None

            # 3) 心跳
            if now >= next_hb:
                next_hb = now + HEARTBEAT_S
                publish({"type": "heartbeat", "uptime": int(now - start_time)}, qos=0)

            time.sleep(TICK_S)
    except KeyboardInterrupt:
        log.info("收到 Ctrl+C, 退出")
    finally:
        if mb is not None:
            mb.close()
        mqtt_client.loop_stop()
        mqtt_client.disconnect()


if __name__ == "__main__":
    main()
