"""温湿度感应器模拟器 - JetLinks 直连版 (方式二)

与 Day1 版的区别:
  1. 直接适配 JetLinks 官方 MQTT 协议, topic 和 payload 格式完全符合 JetLinks 物模型
  2. 通过 EMQX Broker (172.16.4.211:9783, test/123456) 接入, JetLinks 网络组件订阅接收
  3. 属性上报 topic: /{productId}/{deviceId}/properties/report
  4. 监听 JetLinks 下发的 /{productId}/{deviceId}/properties/write, 收到后写 Modbus 并回复

运行: python sensor_simulator_jl.py
依赖: pip install pymodbus==3.6.9 paho-mqtt==1.6.1
"""

import json
import logging
import queue
import time
import uuid
from datetime import datetime

import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient

CONFIG_PATH = "config_jetlinks.json"
DATA_PATH = "sensor_data.json"
RECONNECT_S = 5
TICK_S = 0.2

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("sensor-jl")

# ---------- 运行时变量 ----------
mqtt_client = None
mb_client = None
wq = queue.Queue()           # MQTT 回调 -> 主循环 的命令队列
reg_base = 0
reg_count = 0
unit_id = 1
mb_cfg = {}
mq_cfg = {}
reg_map = {}
store = {}

# JetLinks topic 模板 (从 config 读取 product_id / device_id 再拼)
TOPIC_REPORT = ""     # /{productId}/{deviceId}/properties/report
TOPIC_WRITE = ""      # /{productId}/{deviceId}/properties/write
TOPIC_WRITE_REPLY = "" # /{productId}/{deviceId}/properties/write/reply
TOPIC_READ = ""       # /{productId}/{deviceId}/properties/read
TOPIC_READ_REPLY = "" # /{productId}/{deviceId}/properties/read/reply
TOPIC_INVOKE = ""     # /{productId}/{deviceId}/function/invoke
TOPIC_INVOKE_REPLY = "" # /{productId}/{deviceId}/function/invoke/reply


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


def now_ms():
    """JetLinks 用毫秒时间戳"""
    return int(time.time() * 1000)


def now_s():
    return datetime.now().isoformat(timespec="seconds")


def to_signed(raw):
    return raw - 65536 if raw > 32767 else raw


def parse_values(regs, rm):
    values = {}
    for idx, spec in rm.items():
        i = int(idx)
        if i >= len(regs):
            continue
        raw = to_signed(regs[i]) if spec.get("signed") else regs[i]
        values[spec["name"]] = round(raw * spec.get("scale", 1), 2)
    return values


def gen_message_id():
    return str(uuid.uuid4())[:16]


# ==================== MQTT 发布 ====================

def publish_properties(properties):
    """按 JetLinks 官方协议上报属性"""
    if not TOPIC_REPORT:
        return
    payload = {
        "timestamp": now_ms(),
        "messageId": gen_message_id(),
        "properties": properties
    }
    text = json.dumps(payload, ensure_ascii=False)
    try:
        info = mqtt_client.publish(TOPIC_REPORT, text, qos=1, retain=True)
        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            parts = ["上报属性"]
            for k, v in properties.items():
                parts.append(f"{k}={v}")
            log.info("  ".join(parts))
        else:
            log.warning("发布失败(rc=%s)", info.rc)
    except (OSError, RuntimeError) as e:
        log.warning("MQTT 发布异常: %s", e)


def publish_write_reply(message_id, properties, success=True):
    if not TOPIC_WRITE_REPLY:
        return
    payload = {
        "timestamp": now_ms(),
        "messageId": message_id,
        "success": success,
        "properties": properties
    }
    text = json.dumps(payload, ensure_ascii=False)
    try:
        mqtt_client.publish(TOPIC_WRITE_REPLY, text, qos=1)
        log.info("回复 write/reply  success=%s  properties=%s", success, properties)
    except (OSError, RuntimeError) as e:
        log.warning("回复异常: %s", e)


def publish_read_reply(message_id, properties, success=True):
    if not TOPIC_READ_REPLY:
        return
    payload = {
        "timestamp": now_ms(),
        "messageId": message_id,
        "success": success,
        "properties": properties
    }
    text = json.dumps(payload, ensure_ascii=False)
    try:
        mqtt_client.publish(TOPIC_READ_REPLY, text, qos=1)
        log.info("回复 read/reply  success=%s", success)
    except (OSError, RuntimeError) as e:
        log.warning("回复异常: %s", e)


def publish_invoke_reply(message_id, success=True, properties=None):
    if not TOPIC_INVOKE_REPLY:
        return
    payload = {
        "timestamp": now_ms(),
        "messageId": message_id,
        "success": success,
    }
    if properties:
        payload["properties"] = properties
    text = json.dumps(payload, ensure_ascii=False)
    try:
        mqtt_client.publish(TOPIC_INVOKE_REPLY, text, qos=1)
        log.info("回复 invoke/reply  success=%s", success)
    except (OSError, RuntimeError) as e:
        log.warning("回复异常: %s", e)


# ==================== MQTT 回调 ====================

def on_connect(client, _userdata, _flags, rc):
    if rc != 0:
        log.error("MQTT 连接失败 rc=%s", rc)
        return
    log.info("MQTT 已连接 (EMQX -> JetLinks网络组件)")
    client.subscribe(TOPIC_WRITE, qos=1)
    client.subscribe(TOPIC_READ, qos=1)
    client.subscribe(TOPIC_INVOKE, qos=1)
    wq.put(("report_all",))


def on_disconnect(_client, _userdata, rc):
    log.warning("MQTT 断开 rc=%s, 自动重连中", rc)


def on_message(_client, _userdata, msg):
    text = msg.payload.decode("utf-8", "replace")
    try:
        cmd = json.loads(text)
    except ValueError:
        log.warning("收到非 JSON 消息: %s", text[:80])
        return

    topic = msg.topic
    message_id = cmd.get("messageId", gen_message_id())

    if topic == TOPIC_WRITE:
        properties = cmd.get("properties", {})
        log.info("收到 JetLinks 属性写入命令: %s", properties)
        wq.put(("write_props", message_id, properties))

    elif topic == TOPIC_READ:
        wq.put(("read_props", message_id, cmd.get("properties", [])))

    elif topic == TOPIC_INVOKE:
        func_id = cmd.get("functionId", "")
        params = cmd.get("inputs", cmd.get("properties", {}))
        log.info("收到 JetLinks 功能调用: functionId=%s inputs=%s", func_id, params)
        wq.put(("invoke_func", message_id, func_id, params))

    else:
        log.info("收到未知 topic 消息: %s", topic)


# ==================== Modbus ====================

def modbus_connect():
    global mb_client
    client = ModbusTcpClient(mb_cfg["host"], port=int(mb_cfg["port"]))
    if client.connect():
        log.info("Modbus 已连接 %s:%s", mb_cfg["host"], mb_cfg["port"])
        mb_client = client
        return client
    log.warning("Modbus 连接失败 %s:%s, %ds 后重试", mb_cfg["host"], mb_cfg["port"], RECONNECT_S)
    return None


def modbus_close():
    global mb_client
    if mb_client:
        try:
            mb_client.close()
        except Exception:
            pass
        mb_client = None


# ==================== 主循环 ====================

def main():
    global mqtt_client, mb_client, reg_base, reg_count, unit_id
    global mb_cfg, mq_cfg, reg_map, store
    global TOPIC_REPORT, TOPIC_WRITE, TOPIC_WRITE_REPLY, TOPIC_READ, TOPIC_READ_REPLY
    global TOPIC_INVOKE, TOPIC_INVOKE_REPLY

    cfg = load_json(CONFIG_PATH, {})
    mb_cfg = cfg.get("modbus", {})
    mq_cfg = cfg.get("mqtt", {})
    jl_cfg = cfg.get("jetlinks", {})
    reg_map = cfg.get("register_map", {})

    product_id = jl_cfg.get("product_id", "")
    device_id = jl_cfg.get("device_id", "")

    TOPIC_REPORT = f"/{product_id}/{device_id}/properties/report"
    TOPIC_WRITE = f"/{product_id}/{device_id}/properties/write"
    TOPIC_WRITE_REPLY = f"/{product_id}/{device_id}/properties/write/reply"
    TOPIC_READ = f"/{product_id}/{device_id}/properties/read"
    TOPIC_READ_REPLY = f"/{product_id}/{device_id}/properties/read/reply"
    TOPIC_INVOKE = f"/{product_id}/{device_id}/function/invoke"
    TOPIC_INVOKE_REPLY = f"/{product_id}/{device_id}/function/invoke/reply"

    reg_base = int(mb_cfg.get("register_start", 0))
    reg_count = int(mb_cfg.get("register_count", 10))
    unit_id = int(mb_cfg.get("unit_id", 1))
    poll_s = float(mb_cfg.get("poll_interval", 5))

    store = load_json(DATA_PATH, {"registers": None, "values": None, "last_change": None})

    log.info("JetLinks 模拟器启动 | Modbus %s:%s 0x%04X~0x%04X 每%gs | EMQX %s:%s | 产品 %s 设备 %s",
             mb_cfg["host"], mb_cfg["port"], reg_base, reg_base + reg_count - 1, poll_s,
             mq_cfg.get("host"), mq_cfg.get("port"), product_id, device_id)
    log.info("上报 topic : %s", TOPIC_REPORT)
    log.info("订阅 topic : %s  %s", TOPIC_WRITE, TOPIC_READ)

    # ---- MQTT 连接 (EMQX, test/123456) ----
    client_id = mq_cfg.get("client_id", device_id)
    mqtt_client = mqtt.Client(client_id=client_id, clean_session=True)
    if mq_cfg.get("username"):
        mqtt_client.username_pw_set(mq_cfg["username"], mq_cfg.get("password"))
    mqtt_client.on_connect = on_connect
    mqtt_client.on_disconnect = on_disconnect
    mqtt_client.on_message = on_message
    mqtt_client.reconnect_delay_set(min_delay=5, max_delay=60)
    mqtt_client.connect_async(mq_cfg.get("host", "127.0.0.1"),
                              int(mq_cfg.get("port", 1883)), keepalive=60)
    mqtt_client.loop_start()

    # ---- 主循环 ----
    next_poll = 0.0
    last_retry = 0.0

    try:
        while True:
            now = time.time()

            # 1) 处理 MQTT 下发的命令
            while not wq.empty():
                job = wq.get()
                action = job[0]

                if action == "report_all":
                    if store.get("registers") is not None:
                        publish_properties(store.get("values") or {})

                elif action == "write_props":
                    _, msg_id, properties = job
                    write_results = {}
                    for prop_name, prop_value in properties.items():
                        for reg_offset, spec in reg_map.items():
                            if spec["name"] == prop_name:
                                reg_addr = reg_base + int(reg_offset)
                                reg_value = int(round(prop_value / spec.get("scale", 1)))
                                if mb_client is None and now - last_retry >= RECONNECT_S:
                                    last_retry = now
                                    modbus_connect()
                                if mb_client is None:
                                    log.warning("Modbus 未连接, 无法写入")
                                    break
                                try:
                                    rr = mb_client.write_register(reg_addr, reg_value, slave=unit_id)
                                    if rr.isError():
                                        log.warning("写寄存器 0x%04X 失败: %s", reg_addr, rr)
                                    else:
                                        write_results[prop_name] = prop_value
                                        log.info("写入 寄存器0x%04X = %s (对应 %s=%s)",
                                                 reg_addr, reg_value, prop_name, prop_value)
                                except Exception as e:
                                    log.warning("Modbus 写异常: %s", e)
                                    modbus_close()
                                break
                    success = len(write_results) > 0
                    publish_write_reply(msg_id, write_results if success else properties, success)
                    next_poll = 0

                elif action == "read_props":
                    _, msg_id, prop_list = job
                    if store.get("values"):
                        if prop_list:
                            filtered = {k: store["values"][k] for k in prop_list if k in store["values"]}
                            publish_read_reply(msg_id, filtered, True)
                        else:
                            publish_read_reply(msg_id, store["values"], True)
                    else:
                        publish_read_reply(msg_id, {}, False)

                elif action == "invoke_func":
                    _, msg_id, func_id, params = job
                    # JetLinks 功能调用 inputs 可能是数组格式
                    if isinstance(params, list):
                        params = {item["name"]: item["value"] for item in params if "name" in item and "value" in item}
                    log.info("温湿度功能调用: %s  参数: %s", func_id, params)
                    invoke_results = {}
                    invoke_ok = False

                    # ---- 功能: 设置温度 ----
                    if func_id == "set_temperature":
                        temp_val = params.get("value") or params.get("temperature")
                        try:
                            reg_value = int(float(temp_val) * 10)
                        except (ValueError, TypeError):
                            log.warning("set_temperature 参数无效: %s", temp_val)
                        else:
                            if mb_client is None and now - last_retry >= RECONNECT_S:
                                last_retry = now
                                modbus_connect()
                            if mb_client:
                                try:
                                    rr = mb_client.write_register(reg_base + 0, reg_value, slave=unit_id)
                                    if not rr.isError():
                                        invoke_results["temperature"] = round(reg_value / 10, 2)
                                        invoke_ok = True
                                        log.info("功能调用 set_temperature: %.1f°C ✅", reg_value / 10)
                                except Exception as e:
                                    log.warning("Modbus 写温度异常: %s", e)
                                    modbus_close()

                    # ---- 功能: 设置湿度 ----
                    elif func_id == "set_humidity":
                        hum_val = params.get("value") or params.get("humidity")
                        try:
                            reg_value = int(float(hum_val) * 10)
                        except (ValueError, TypeError):
                            log.warning("set_humidity 参数无效: %s", hum_val)
                        else:
                            if mb_client is None and now - last_retry >= RECONNECT_S:
                                last_retry = now
                                modbus_connect()
                            if mb_client:
                                try:
                                    rr = mb_client.write_register(reg_base + 1, reg_value, slave=unit_id)
                                    if not rr.isError():
                                        invoke_results["humidity"] = round(reg_value / 10, 2)
                                        invoke_ok = True
                                        log.info("功能调用 set_humidity: %.1f%% ✅", reg_value / 10)
                                except Exception as e:
                                    log.warning("Modbus 写湿度异常: %s", e)
                                    modbus_close()

                    # ---- 功能: 设置温湿度 ----
                    elif func_id == "set_both":
                        temp_val = params.get("temperature")
                        hum_val = params.get("humidity")
                        if mb_client is None and now - last_retry >= RECONNECT_S:
                            last_retry = now
                            modbus_connect()
                        if mb_client:
                            if temp_val is not None:
                                try:
                                    rr = mb_client.write_register(reg_base + 0, int(float(temp_val) * 10), slave=unit_id)
                                    if not rr.isError():
                                        invoke_results["temperature"] = float(temp_val)
                                except Exception:
                                    pass
                            if hum_val is not None:
                                try:
                                    rr = mb_client.write_register(reg_base + 1, int(float(hum_val) * 10), slave=unit_id)
                                    if not rr.isError():
                                        invoke_results["humidity"] = float(hum_val)
                                except Exception:
                                    pass
                            invoke_ok = len(invoke_results) > 0
                            log.info("功能调用 set_both: %s ✅", invoke_results)

                    # ---- 功能: 查询状态 ----
                    elif func_id == "get_status":
                        if store.get("values"):
                            invoke_results = dict(store["values"])
                            invoke_ok = True
                            log.info("功能调用 get_status: %s ✅", invoke_results)

                    # ---- 通用功能: 属性名=值 ----
                    else:
                        for prop_name, prop_value in params.items():
                            for reg_offset, spec in reg_map.items():
                                if spec["name"] == prop_name:
                                    reg_addr = reg_base + int(reg_offset)
                                    reg_value = int(float(prop_value) / spec.get("scale", 1))
                                    if mb_client is None and now - last_retry >= RECONNECT_S:
                                        last_retry = now
                                        modbus_connect()
                                    if mb_client:
                                        try:
                                            rr = mb_client.write_register(reg_addr, reg_value, slave=unit_id)
                                            if not rr.isError():
                                                invoke_results[prop_name] = prop_value
                                                invoke_ok = True
                                                log.info("功能调用 %s: %s=%s ✅", func_id, prop_name, prop_value)
                                        except Exception as e:
                                            log.warning("Modbus 写异常: %s", e)
                                            modbus_close()
                                    break

                    publish_invoke_reply(msg_id, invoke_ok, invoke_results)
                    # 功能调用后主动上报
                    if invoke_ok:
                        try:
                            rr = mb_client.read_holding_registers(reg_base, count=reg_count, slave=unit_id)
                            if not rr.isError():
                                regs = list(rr.registers)
                                values = parse_values(regs, reg_map)
                                store["registers"] = regs
                                store["values"] = values
                                store["last_change"] = now_s()
                                save_json(DATA_PATH, store)
                                publish_properties(values)
                        except Exception as e:
                            log.warning("功能调用后读取失败: %s", e)

            # 2) 周期采集 Modbus → 变化检测 → JetLinks 格式上报
            if now >= next_poll:
                next_poll = now + poll_s
                if mb_client is None and now - last_retry >= RECONNECT_S:
                    last_retry = now
                    modbus_connect()
                if mb_client is not None:
                    try:
                        rr = mb_client.read_holding_registers(reg_base, count=reg_count, slave=unit_id)
                        if rr.isError():
                            raise RuntimeError(str(rr))
                        regs = list(rr.registers)
                        if regs != store.get("registers"):
                            values = parse_values(regs, reg_map)
                            store["registers"] = regs
                            store["values"] = values
                            store["last_change"] = now_s()
                            save_json(DATA_PATH, store)
                            publish_properties(values)
                    except Exception as e:
                        log.warning("Modbus 读取失败: %s", e)
                        modbus_close()

            time.sleep(TICK_S)

    except KeyboardInterrupt:
        log.info("收到 Ctrl+C, 退出")
    finally:
        modbus_close()
        if mqtt_client:
            mqtt_client.loop_stop()
            mqtt_client.disconnect()


if __name__ == "__main__":
    main()
