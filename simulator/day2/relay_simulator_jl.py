"""继电器设备模拟器 - JetLinks 直连版

继电器设备扩展:
  - 4 路继电器开关 (relay1~relay4), 对应 Modbus 寄存器 0x0002~0x0005
  - 电流、电压监测, 对应寄存器 0x0006~0x0007
  - 继电器状态变化时立即上报 (不是周期轮询才上报)
  - 支持 JetLinks 平台下发 write 命令远程控制继电器

运行: python relay_simulator_jl.py
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

CONFIG_PATH = "config_relay.json"
DATA_PATH = "relay_data.json"
RECONNECT_S = 5
TICK_S = 0.2

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(message)s",
                    datefmt="%H:%M:%S")
log = logging.getLogger("relay-jl")

# ---------- 运行时变量 ----------
mqtt_client = None
mb_client = None
wq = queue.Queue()
reg_base = 2
reg_count = 6
unit_id = 1
mb_cfg = {}
mq_cfg = {}
reg_map = {}
store = {}

TOPIC_REPORT = ""
TOPIC_WRITE = ""
TOPIC_WRITE_REPLY = ""
TOPIC_READ = ""
TOPIC_READ_REPLY = ""
TOPIC_INVOKE = ""
TOPIC_INVOKE_REPLY = ""


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
        val = round(raw * spec.get("scale", 1), 2)
        # 继电器开关量钳位: 强制转为 0/1, 防止从站返回脏值导致 JetLinks 拒收
        if spec["name"].startswith("relay"):
            val = 1 if val else 0
        values[spec["name"]] = val
    return values


def gen_message_id():
    return str(uuid.uuid4())[:16]


# ==================== MQTT 发布 ====================

def publish_properties(properties):
    if not TOPIC_REPORT:
        return
    payload = {
        "timestamp": now_ms(),
        "messageId": gen_message_id(),
        "properties": properties
    }
    text = json.dumps(payload, ensure_ascii=False)
    try:
        info = mqtt_client.publish(TOPIC_REPORT, text, qos=1, retain=False)
        if info.rc == mqtt.MQTT_ERR_SUCCESS:
            parts = ["上报属性"]
            for k, v in properties.items():
                unit = ""
                for spec in reg_map.values():
                    if spec["name"] == k:
                        unit = spec.get("unit", "")
                        break
                parts.append(f"{k}={v}{unit}")
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
        relay_names = []
        for k, v in properties.items():
            if k.startswith("relay"):
                relay_names.append(f"{k}={'开' if v else '关'}")
        extra = f"  [{', '.join(relay_names)}]" if relay_names else ""
        log.info("回复 write/reply  success=%s  properties=%s%s", success, properties, extra)
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
    log.info("MQTT 已连接")
    # 清除 EMQX 上残留的旧 retained 消息 (空 payload + retain=True = 删除)
    client.publish(TOPIC_REPORT, "", qos=1, retain=True)
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
        # 解析继电器属性, 把布尔/开关语义转成 0/1
        normalized = {}
        for name, val in properties.items():
            if name.startswith("relay"):
                if isinstance(val, bool):
                    normalized[name] = 1 if val else 0
                elif isinstance(val, str):
                    normalized[name] = 1 if val.lower() in ("1", "on", "open", "true") else 0
                else:
                    normalized[name] = int(val) if int(val) in (0, 1) else 0
            else:
                normalized[name] = val
        wq.put(("write_props", message_id, normalized))

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


def set_relay_by_name(name, value):
    """辅助函数: 按名称写继电器寄存器, 返回 (是否成功, 寄存器地址)"""
    relay_value = 1 if value else 0
    for reg_offset, spec in reg_map.items():
        if spec["name"] == name and name.startswith("relay"):
            reg_addr = reg_base + int(reg_offset)
            if mb_client is None:
                return False, None
            try:
                rr = mb_client.write_register(reg_addr, relay_value, slave=unit_id)
                if not rr.isError():
                    return True, reg_addr
            except Exception as e:
                log.warning("写 %s 失败: %s", name, e)
                modbus_close()
            return False, reg_addr
    return False, None


def read_all_relays():
    """辅助函数: 读取所有寄存器并解析"""
    if mb_client is None:
        return None
    try:
        rr = mb_client.read_holding_registers(reg_base, count=reg_count, slave=unit_id)
        if rr.isError():
            return None
        regs = list(rr.registers)
        values = parse_values(regs, reg_map)
        return values
    except Exception:
        return None


def reconnect_if_needed(now_var, last_retry_var):
    """辅助函数: Modbus 断线重连"""
    if mb_client is None and now_var - last_retry_var >= RECONNECT_S:
        last_retry_var[0] = now_var
        modbus_connect()
    return mb_client is not None


# ==================== MQTT 主循环 ====================

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
    relay_order = cfg.get("relay_order", [])

    product_id = jl_cfg.get("product_id", "")
    device_id = jl_cfg.get("device_id", "")

    TOPIC_REPORT = f"/{product_id}/{device_id}/properties/report"
    TOPIC_WRITE = f"/{product_id}/{device_id}/properties/write"
    TOPIC_WRITE_REPLY = f"/{product_id}/{device_id}/properties/write/reply"
    TOPIC_READ = f"/{product_id}/{device_id}/properties/read"
    TOPIC_READ_REPLY = f"/{product_id}/{device_id}/properties/read/reply"
    TOPIC_INVOKE = f"/{product_id}/{device_id}/function/invoke"
    TOPIC_INVOKE_REPLY = f"/{product_id}/{device_id}/function/invoke/reply"

    reg_base = int(mb_cfg.get("register_start", 2))
    reg_count = int(mb_cfg.get("register_count", 6))
    unit_id = int(mb_cfg.get("unit_id", 1))
    poll_s = float(mb_cfg.get("poll_interval", 3))

    store = load_json(DATA_PATH, {"registers": None, "values": None, "last_change": None})
    # 启动时清空缓存, 防止旧从站的残留数据先上报导致 JetLinks 闪跳
    store["registers"] = None
    store["values"] = None

    log.info("继电器模拟器启动 | Modbus %s:%s 寄存器 0x%04X~0x%04X 每%gs | EMQX %s:%s | 产品 %s 设备 %s",
             mb_cfg["host"], mb_cfg["port"], reg_base, reg_base + reg_count - 1, poll_s,
             mq_cfg.get("host"), mq_cfg.get("port"), product_id, device_id)
    log.info("继电器映射: " + ", ".join(f"{r['name']}→reg{r['register']}" for r in relay_order))
    log.info("上报 topic : %s", TOPIC_REPORT)
    log.info("订阅 topic : %s  %s  %s", TOPIC_WRITE, TOPIC_READ, TOPIC_INVOKE)

    # ---- MQTT 连接 ----
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
                                        state = "开" if prop_value else "关"
                                        if prop_name.startswith("relay"):
                                            log.info("继电器 %s → %s  (寄存器0x%04X=%s)",
                                                     prop_name, state, reg_addr, reg_value)
                                        else:
                                            log.info("写入 寄存器0x%04X = %s (对应 %s=%s)",
                                                     reg_addr, reg_value, prop_name, prop_value)
                                except Exception as e:
                                    log.warning("Modbus 写异常: %s", e)
                                    modbus_close()
                                break
                    success = len(write_results) > 0
                    publish_write_reply(msg_id, write_results if success else properties, success)
                    # 写入后主动上报最新状态 (不等轮询)
                    if success:
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
                            log.warning("写入后读取失败: %s", e)

                elif action == "invoke_func":
                    _, msg_id, func_id, params = job
                    # JetLinks 功能调用 inputs 可能是数组格式: [{'name':'relay','value':2}, ...]
                    # 也可能是字典格式: {'relay': 2, 'state': 1}
                    if isinstance(params, list):
                        params = {item["name"]: item["value"] for item in params if "name" in item and "value" in item}
                    log.info("处理功能调用: %s  参数: %s", func_id, params)
                    invoke_results = {}
                    invoke_ok = False

                    # ---- 功能: 全部打开 ----
                    if func_id == "all_on":
                        if reconnect_if_needed(now, [last_retry]):
                            for reg_offset, spec in reg_map.items():
                                name = spec["name"]
                                if name.startswith("relay"):
                                    ok, _ = set_relay_by_name(name, True)
                                    if ok:
                                        invoke_results[name] = 1
                            invoke_ok = len(invoke_results) > 0
                            log.info("功能调用 all_on: 打开 %d 路 ✅", len(invoke_results))

                    # ---- 功能: 全部关闭 ----
                    elif func_id == "all_off":
                        if reconnect_if_needed(now, [last_retry]):
                            for reg_offset, spec in reg_map.items():
                                name = spec["name"]
                                if name.startswith("relay"):
                                    ok, _ = set_relay_by_name(name, False)
                                    if ok:
                                        invoke_results[name] = 0
                            invoke_ok = len(invoke_results) > 0
                            log.info("功能调用 all_off: 关闭 %d 路 ✅", len(invoke_results))

                    # ---- 功能: 设置单个继电器 ----
                    elif func_id == "set_relay":
                        relay_num = params.get("relay") or params.get("channel")
                        state = params.get("state", params.get("value", params.get("status", 1)))
                        try:
                            relay_idx = int(relay_num)
                            relay_name = f"relay{relay_idx}"
                            on = bool(int(state))
                        except (ValueError, TypeError):
                            log.warning("set_relay 参数无效: relay=%s state=%s", relay_num, state)
                        else:
                            if reconnect_if_needed(now, [last_retry]):
                                ok, reg_addr = set_relay_by_name(relay_name, on)
                                if ok:
                                    invoke_results[relay_name] = 1 if on else 0
                                    invoke_ok = True
                                    log.info("功能调用 set_relay: %s → %s  ✅", relay_name, "开" if on else "关")
                                elif reg_addr is not None:
                                    log.warning("set_relay: 未找到 %s", relay_name)

                    # ---- 功能: 切换指定继电器 ----
                    elif func_id == "toggle":
                        relay_num = params.get("relay", 1)
                        try:
                            relay_idx = int(relay_num)
                            relay_name = f"relay{relay_idx}"
                        except (ValueError, TypeError):
                            log.warning("toggle 参数 relay 无效: %s", relay_num)
                        else:
                            if reconnect_if_needed(now, [last_retry]):
                                values = read_all_relays()
                                if values and relay_name in values:
                                    old_val = values[relay_name]
                                    new_val = 0 if old_val else 1
                                    ok, _ = set_relay_by_name(relay_name, new_val)
                                    if ok:
                                        invoke_results[relay_name] = new_val
                                        invoke_ok = True
                                        log.info("功能调用 toggle: %s %d→%d ✅", relay_name, old_val, new_val)

                    # ---- 功能: 批量设置 ----
                    elif func_id == "set_batch":
                        relays_str = params.get("relays", "")  # 如 "1,3,5-8"
                        state = params.get("state", 1)
                        on = bool(int(state))
                        relay_nums = []
                        for part in str(relays_str).split(","):
                            part = part.strip()
                            if "-" in part:
                                lo, hi = part.split("-", 1)
                                relay_nums.extend(range(int(lo), int(hi) + 1))
                            elif part:
                                relay_nums.append(int(part))
                        if reconnect_if_needed(now, [last_retry]):
                            for n in relay_nums:
                                relay_name = f"relay{n}"
                                ok, _ = set_relay_by_name(relay_name, on)
                                if ok:
                                    invoke_results[relay_name] = 1 if on else 0
                            invoke_ok = len(invoke_results) > 0
                            log.info("功能调用 set_batch: %s → %s  成功 %d 路 ✅",
                                     relays_str, "开" if on else "关", len(invoke_results))

                    # ---- 功能: 查询状态 ----
                    elif func_id == "get_status":
                        values = read_all_relays()
                        if values:
                            invoke_results = {k: v for k, v in values.items() if k.startswith("relay")}
                            invoke_ok = True
                            log.info("功能调用 get_status: %s ✅", invoke_results)

                    # ---- 通用功能: 参数是属性名=值 (兼容旧逻辑) ----
                    else:
                        for prop_name, prop_value in params.items():
                            if prop_name.startswith("relay"):
                                on = bool(int(prop_value))
                                ok, _ = set_relay_by_name(prop_name, on)
                                if ok:
                                    invoke_results[prop_name] = 1 if on else 0
                                    invoke_ok = True
                                    log.info("功能调用 %s: %s=%s ✅", func_id, prop_name, invoke_results[prop_name])

                    publish_invoke_reply(msg_id, invoke_ok, invoke_results)
                    # 功能调用后也主动上报最新状态
                    if invoke_ok:
                        values = read_all_relays()
                        if values:
                            store["values"] = values
                            store["registers"] = None
                            store["last_change"] = now_s()
                            save_json(DATA_PATH, store)
                            publish_properties(values)

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
