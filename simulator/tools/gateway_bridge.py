"""Day9 Gateway Bridge: ESP32 网关 ↔ 多虚拟设备 协议转换服务

架构:
  ESP32 (单网关产品 relay-cc/relaycc)
    │ 发所有数据到 /relay-cc/relaycc/properties/report
    │ payload: {properties: {relay1:1, relay2:0, temperature:26.5, human:0, ...}}
    ↓
  Python Bridge (本程序)
    ├── 订阅 /relay-cc/relaycc/# (上行)
    │   按 ROUTING TABLE 拆分每个 key
    │   转发到各自的虚拟产品 topic
    │
    └── 订阅所有虚拟产品的下行 topic (下行)
        收到平台对虚拟产品的 write/invoke
        按 DOWNLINK TABLE 路由回网关

  硬编码路由表:
    relay1 → lock-cc / lock001  (门锁)
    relay2 → light-cc / light001 (灯1)
    relay3 → light-cc / light002 (灯2)
    relay4 → ac-cc    / ac001    (空调)
    temperature → sensor-cc / sensorcc
    humidity    → sensor-cc / sensorcc
    human       → human-cc / human001
    smoke       → smoke-cc / smoke001
    current     → sensor-cc / sensorcc  (可选)
    voltage     → sensor-cc / sensorcc  (可选)

运行:
  pip install paho-mqtt
  python gateway_bridge.py
"""
import json
import time
import threading
from paho.mqtt import client as mqtt_client

# ============================================================
# 连接配置
# ============================================================
MQTT_HOST = "172.16.4.211"
MQTT_PORT = 9783
MQTT_USER = "test"
MQTT_PASS = "123456"

# 网关产品 (ESP32 直接连的)
GATEWAY_PRODUCT = "relay-cc"
GATEWAY_DEVICE  = "relaycc"

# Bridge 自己的 client_id (要唯一)
BRIDGE_CLIENT_ID = "bridge-python-v1"

# ============================================================
# 上行路由表 (Gateway key → Virtual Product + property name)
# ============================================================
UP_ROUTING = {
    # GPIO 继电器通道
    "relay1": {
        "product": "lock-cc", "device": "lock001", "property": "switch",
    },
    "relay2": {
        "product": "light-cc", "device": "light001", "property": "switch",
    },
    "relay3": {
        "product": "light-cc", "device": "light002", "property": "switch",
    },
    "relay4": {
        "product": "ac-cc", "device": "ac001", "property": "switch",
    },
    # Modbus 温湿度 (一个 product, 两个属性)
    "temperature": {
        "product": "sensor-cc", "device": "sensorcc", "property": "temperature",
    },
    "humidity": {
        "product": "sensor-cc", "device": "sensorcc", "property": "humidity",
    },
    # Modbus 模拟多寄存器
    "human": {
        "product": "human-cc", "device": "human001", "property": "detected",
    },
    "smoke": {
        "product": "smoke-cc", "device": "smoke001", "property": "level",
    },
}

# ============================================================
# 下行路由表 (Virtual Product + property → Gateway key)
# 自动从 UP_ROUTING 反向生成, 不需要手动写
# ============================================================
def _build_down_routing():
    """UP_ROUTING 反向: (product, device, property) → gateway_key"""
    down = {}
    for gw_key, info in UP_ROUTING.items():
        key = (info["product"], info["device"], info["property"])
        down[key] = gw_key
    return down

DOWN_ROUTING = _build_down_routing()

# 所有虚拟产品列表 (用于订阅它们的下行 topic)
VIRTUAL_PRODUCTS = sorted(set(info["product"] for info in UP_ROUTING.values()))
VIRTUAL_DEVICES = {}  # product → [devices]
for info in UP_ROUTING.values():
    VIRTUAL_DEVICES.setdefault(info["product"], set()).add(info["device"])

print("=" * 60)
print("Day9 Gateway Bridge")
print("=" * 60)
print(f"网关产品: {GATEWAY_PRODUCT}/{GATEWAY_DEVICE}")
print(f"MQTT: {MQTT_HOST}:{MQTT_PORT}")
print(f"虚拟产品 ({len(VIRTUAL_PRODUCTS)} 个): {', '.join(VIRTUAL_PRODUCTS)}")
print(f"路由表 ({len(UP_ROUTING)} 个 key):")
for gw_key, info in sorted(UP_ROUTING.items()):
    print(f"  {gw_key:15s} → {info['product']:12s}/{info['device']:10s} ({info['property']})")
print("=" * 60)

# ============================================================
# 主题构造
# ============================================================
def t(base, product, device, suffix):
    """{product}/{device}/{suffix}"""
    return f"{base}/{product}/{device}/{suffix}"


def _build_gateway_topics():
    """网关的所有下行 topic (Bridge 发布命令到此)"""
    base = f"{GATEWAY_PRODUCT}/{GATEWAY_DEVICE}"
    return {
        "report":      base + "/properties/report",
        "event":       base + "/event",
        "write":       base + "/properties/write",
        "write_reply": base + "/properties/write/reply",
        "read":        base + "/properties/read",
        "read_reply":  base + "/properties/read/reply",
        "invoke":      base + "/function/invoke",
        "invoke_reply":base + "/function/invoke/reply",
    }

GATEWAY_TOPICS = _build_gateway_topics()


def virtual_topic(product, device, suffix):
    """虚拟产品的 topic (JetLinks 要求前导 /)"""
    return f"/{product}/{device}/{suffix}"


# ============================================================
# 消息 ID 映射 (下行时跟踪: 虚拟设备 requestId → 网关 requestId)
# 这样 Bridge 才能把网关的 reply 发回正确的虚拟设备 topic
# ============================================================
_msg_map_lock = threading.Lock()
_msg_map = {}  # bridge_msg_id → {"origin": (product, device, reply_key), "bridge_id": new_id, "timestamp": ts}


def _next_bridge_id():
    return f"bridge-{int(time.time()*1000) % 1000000000}-{threading.get_ident() % 1000}"


def _store_reply_mapping(origin_product, origin_device, reply_key, bridge_msg_id, origin_msg_id):
    """当 Bridge 收到平台对虚拟设备的命令时, 记录映射以便正确回复"""
    now = time.time()
    with _msg_map_lock:
        # 清理超过 30 秒的陈旧 entry (ESP32 没回复的情况)
        stale = [k for k, v in _msg_map.items() if now - v["ts"] > 30]
        for k in stale:
            del _msg_map[k]
        # 保持 _msg_map 不超过 200 条
        if len(_msg_map) > 200:
            oldest_keys = sorted(_msg_map.keys(), key=lambda k: _msg_map[k]["ts"])[:len(_msg_map) - 150]
            for k in oldest_keys:
                del _msg_map[k]

        _msg_map[bridge_msg_id] = {
            "origin_product": origin_product,
            "origin_device": origin_device,
            "origin_msg_id": origin_msg_id,
            "reply_key": reply_key,
            "bridge_msg_id": bridge_msg_id,
            "ts": now,
        }


def _get_reply_target(bridge_msg_id):
    """网关 reply 到来时, 找到对应的虚拟产品 + original msg_id"""
    with _msg_map_lock:
        entry = _msg_map.pop(bridge_msg_id, None)
    return entry


# ============================================================
# 上行: 网关 → 虚拟设备
# ============================================================
def handle_gateway_properties_report(payload):
    """处理网关的 properties/report, 按 routing table 拆分转发"""
    props = payload.get("properties", {})
    ts = payload.get("timestamp", int(time.time() * 1000))
    bridge_mid = payload.get("messageId", _next_bridge_id())

    # 按 (product, device) 聚合 key
    by_virtual = {}  # (product, device) → {property: value}
    for gw_key, value in props.items():
        info = UP_ROUTING.get(gw_key)
        if not info:
            # 这个 gateway key 没配路由, 跳过
            continue
        vkey = (info["product"], info["device"])
        by_virtual.setdefault(vkey, {})[info["property"]] = value

    # 转发到各虚拟产品
    forwarded = 0
    for (product, device), vprops in by_virtual.items():
        report_topic = virtual_topic(product, device, "properties/report")
        new_payload = {
            "timestamp": ts,
            "messageId": f"{bridge_mid}-{product}-{device}",
            "properties": vprops,
        }
        _BRIDGE_PUBLISHER.publish(report_topic, json.dumps(new_payload), qos=1)
        print(f"  ↑ {product}/{device} report: {vprops}")
        forwarded += 1

    print(f"↑ 网关上报 {len(props)} 个 key → 转发 {forwarded} 个虚拟设备")


# ============================================================
# 下行: 虚拟设备 → 网关
# ============================================================
def handle_virtual_write(product, device, payload):
    """虚拟设备 properties/write → 网关 write"""
    props = payload.get("properties", {})
    origin_mid = payload.get("messageId", _next_bridge_id())
    ts = payload.get("timestamp", int(time.time() * 1000))

    # 路由: 虚拟产品 property → gateway relay key
    gw_props = {}
    for vprop, vval in props.items():
        gw_key = DOWN_ROUTING.get((product, device, vprop))
        if gw_key:
            gw_props[gw_key] = vval
        else:
            print(f"  ! 未配置的下行映射: ({product},{device},{vprop})")

    if not gw_props:
        print(f"  ↓ 虚拟 write 无有效路由: {product}/{device} → {props}")
        return

    bridge_mid = _next_bridge_id()
    bridge_payload = {
        "timestamp": ts,
        "messageId": bridge_mid,
        "properties": gw_props,
    }
    _store_reply_mapping(product, device, "write_reply", bridge_mid, origin_mid)
    _BRIDGE_PUBLISHER.publish(GATEWAY_TOPICS["write"], json.dumps(bridge_payload), qos=1)
    print(f"  ↓ {product}/{device} write {props} → gateway {gw_props}")


def handle_virtual_invoke(product, device, payload):
    """虚拟设备 function/invoke → 网关 invoke 或 write"""
    origin_mid = payload.get("messageId", _next_bridge_id())
    ts = payload.get("timestamp", int(time.time() * 1000))
    fid = payload.get("functionId", "")
    inputs = payload.get("inputs", payload.get("properties", {}))
    if isinstance(inputs, list):
        inputs = {i.get("name"): i.get("value") for i in inputs if isinstance(i, dict)}

    # 虚拟产品的 write 功能 → 转换成网关属性写入 (和 properties/write 一样路由)
    if fid == "write":
        handle_virtual_write(product, device, {
            "messageId": origin_mid,
            "timestamp": ts,
            "properties": inputs,
        })
        return

    # 其他功能直接透传到网关
    bridge_mid = _next_bridge_id()
    bridge_payload = {
        "timestamp": ts,
        "messageId": bridge_mid,
        "functionId": fid,
        "inputs": inputs,
    }
    _store_reply_mapping(product, device, "invoke_reply", bridge_mid, origin_mid)
    _BRIDGE_PUBLISHER.publish(GATEWAY_TOPICS["invoke"], json.dumps(bridge_payload), qos=1)
    print(f"  ↓ {product}/{device} invoke {fid} {inputs}")


# ============================================================
# 网关 reply → 虚拟设备 reply
# ============================================================
def handle_gateway_reply(reply_key, payload):
    """网关 reply (write_reply / invoke_reply / read_reply) → 路由回虚拟设备"""
    bridge_mid = payload.get("messageId", "")
    ts = payload.get("timestamp", int(time.time() * 1000))
    entry = _get_reply_target(bridge_mid)
    if not entry:
        # 这是网关自己的 reply (比如 ESP32 重启后的首次 write_reply, 没有 origin 映射)
        print(f"  ? 网关 {reply_key} 无映射: {bridge_mid}")
        return

    # 重建 payload 用原始 messageId
    origin_payload = dict(payload)
    origin_payload["messageId"] = entry["origin_msg_id"]
    # 移除可能添加的 bridge 字段

    # publish 到虚拟设备的 reply topic
    reply_topic = virtual_topic(entry["origin_product"], entry["origin_device"], entry["reply_key"])
    _BRIDGE_PUBLISHER.publish(reply_topic, json.dumps(origin_payload), qos=1)
    print(f"  → gateway {reply_key} → {entry['origin_product']}/{entry['origin_device']} {entry['reply_key']}")


# ============================================================
# MQTT 回调
# ============================================================
def on_connect(client, userdata, flags, rc):
    """连上后订阅所有需要的 topic"""
    if rc != 0:
        print(f"[Bridge] 连接失败 rc={rc}")
        return
    print(f"[Bridge] 已连接 {MQTT_HOST}:{MQTT_PORT}")

    # 订阅网关所有上行消息
    client.subscribe(f"{GATEWAY_PRODUCT}/{GATEWAY_DEVICE}/#", qos=1)
    print(f"  订阅网关: {GATEWAY_PRODUCT}/{GATEWAY_DEVICE}/#")

    # 订阅所有虚拟产品的下行消息 (write, read, invoke)
    for product, devices in VIRTUAL_DEVICES.items():
        for device in devices:
            suffixes = ["properties/write", "properties/read", "function/invoke"]
            for suffix in suffixes:
                topic = virtual_topic(product, device, suffix)
                client.subscribe(topic, qos=1)
            print(f"  订阅虚拟下行: {product} ({len(devices)} 设备)")


def on_message(client, userdata, msg):
    """分发所有收到的消息"""
    raw = msg.payload.decode() if msg.payload else ""
    t = msg.topic
    print(f"[Bridge RAW] {t} -> {raw[:80]}")
    # ESP32 会发 retain=True 的空 payload 作为在线标记, 跳过
    if not raw:
        return
    try:
        payload = json.loads(raw)
    except Exception as e:
        print(f"[Bridge] 无法解析消息: topic={t[:60]} payload={raw[:80]} err={e}")
        return

    # --- 判断是网关消息还是虚拟产品消息 ---
    gateway_prefix = f"{GATEWAY_PRODUCT}/{GATEWAY_DEVICE}/"
    if t.startswith(gateway_prefix):
        handle_gateway_message(t, payload)
    else:
        handle_virtual_message(t, payload)


def handle_gateway_message(topic, payload):
    """网关 topic 消息分发"""
    # topic = relay-cc/relaycc/properties/report
    # 去掉前缀 relay-cc/relaycc/
    prefix = f"{GATEWAY_PRODUCT}/{GATEWAY_DEVICE}/"
    suffix = topic[len(prefix):] if topic.startswith(prefix) else topic

    if suffix == "properties/report":
        handle_gateway_properties_report(payload)
    elif suffix.startswith("event/"):
        evt = suffix.split("/", 1)[1]
        print(f"  ↑ 网关 event: {evt}")
    elif suffix == "properties/write/reply":
        handle_gateway_reply("write_reply", payload)
    elif suffix == "function/invoke/reply":
        handle_gateway_reply("invoke_reply", payload)
    elif suffix == "properties/read/reply":
        handle_gateway_reply("read_reply", payload)
    else:
        pass


def handle_virtual_message(topic, payload):
    """虚拟产品 topic 消息分发 → 路由回网关
    兼容带或不带前导 / 的 topic:
      带 / : /product/device/properties/write → parts = ['', product, device, ...]
      不带 /: product/device/properties/write → parts = [product, device, ...]
    """
    parts = topic.split("/")
    if len(parts) < 4:
        return
    # 去掉可能的前导空字符串
    if parts[0] == "":
        parts = parts[1:]
    if len(parts) < 3:
        return
    product = parts[0]
    device = parts[1]
    suffix = "/".join(parts[2:])

    if suffix == "properties/write":
        handle_virtual_write(product, device, payload)
    elif suffix == "function/invoke":
        handle_virtual_invoke(product, device, payload)
    elif suffix == "properties/read":
        # read 暂时也路由回网关 (ESP32 网关有 read handler)
        bridge_mid = _next_bridge_id()
        bridge_payload = {
            "timestamp": payload.get("timestamp", int(time.time() * 1000)),
            "messageId": bridge_mid,
        }
        # 复制 properties 数组 (read 请求可以指定要读哪些属性)
        if "properties" in payload:
            bridge_payload["properties"] = payload["properties"]
        _store_reply_mapping(product, device, "read_reply", bridge_mid,
                             payload.get("messageId", bridge_mid))
        _BRIDGE_PUBLISHER.publish(GATEWAY_TOPICS["read"], json.dumps(bridge_payload), qos=1)
        print(f"  ↓ {product}/{device} read")
    # write_reply / invoke_reply / read_reply 是网关来的 reply, 在 handle_gateway_reply 里处理


# ============================================================
# 主程序
# ============================================================
_BRIDGE_PUBLISHER = None


def on_log(client, userdata, level, buf):
    if level >= 16:  # 只打印 MQTT 协议级别日志
        pass  # 注释掉避免噪音

def main():
    global _BRIDGE_PUBLISHER

    client = mqtt_client.Client(
        client_id=BRIDGE_CLIENT_ID,
        clean_session=True,
    )
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message
    client.on_log = on_log
    print("[Bridge] connecting...")
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=60)

    _BRIDGE_PUBLISHER = client

    print("[Bridge] loop_forever...")
    client.loop_forever()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Bridge] 退出")
