"""Day9 Gateway Bridge: ESP32 网关 ↔ 多虚拟设备 协议转换服务

与 Day8 区别:
  - UP_ROUTING 从 SQLite 数据库 (db/iot_platform.db) 动态加载,
    不再硬编码. 通过 Web 管理界面增删改映射后, Bridge 可热重载.
  - 支持 --hot-reload 参数: 每 5 秒自动从 SQLite 刷新路由表.
    默认关闭 (启动时加载一次, 节省数据库查询).

运行:
  pip install paho-mqtt flask
  python gateway_bridge.py              # 启动时加载一次路由
  python gateway_bridge.py --hot-reload # 每 5 秒自动刷新路由表
"""
import json
import time
import threading
import argparse
import os
import sys

# 把 day9/ 目录加入 sys.path, 让 db.py 可被导入
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

from db import init_db, load_routing, load_all_mappings, update_device_status  # SQLite 数据层

from paho.mqtt import client as mqtt_client

# ============================================================
# 连接配置: 统一从 esp32_firmware/config.json 读取, 避免多处硬编码
# ============================================================
from db import load_gateway_config
_cfg = load_gateway_config()

MQTT_HOST = _cfg["mqtt_host"]
MQTT_PORT = _cfg["mqtt_port"]
MQTT_USER = _cfg["mqtt_user"]
MQTT_PASS = _cfg["mqtt_pass"]

# 网关产品 (ESP32 直接连的)
GATEWAY_PRODUCT = _cfg["product_id"]
GATEWAY_DEVICE  = _cfg["device_id"]

# Bridge 自己的 client_id (要唯一)
BRIDGE_CLIENT_ID = "bridge-day9-v1"

# ============================================================
# 动态路由表: 从 SQLite 加载, 支持热重载
# ============================================================
_routing_lock = threading.Lock()
UP_ROUTING = {}          # {gateway_key: {product, device, property}}
DOWN_ROUTING = {}        # {(product, device, property): gateway_key}
VIRTUAL_PRODUCTS = []    # 虚拟产品列表
VIRTUAL_DEVICES = {}     # product → set(devices)


def _rebuild_all(routing: dict):
    """根据新路由表重建 DOWN_ROUTING (仅启用).
    VIRTUAL_PRODUCTS / VIRTUAL_DEVICES 由全部映射(含禁用)构建,
    确保 Bridge 始终订阅所有虚拟 topic, 禁用的映射在路由时才拦截.
    """
    global DOWN_ROUTING, VIRTUAL_PRODUCTS, VIRTUAL_DEVICES
    down = {}
    for gw_key, info in routing.items():
        key = (info["product"], info["device"], info["property"])
        down[key] = gw_key
    DOWN_ROUTING = down

    # 订阅信息从全部映射构建 (含禁用), 确保始终订阅所有 topic
    try:
        all_mappings = load_all_mappings()
    except Exception:
        all_mappings = []
    all_products = set()
    all_devices = {}
    for m in all_mappings:
        enabled = m.get("enabled", 1)
        if enabled:
            info = routing.get(m["gateway_key"], {})
            if info:
                all_products.add(info.get("product", ""))
                all_devices.setdefault(info["product"], set()).add(info["device"])
        else:
            info = routing.get(m["gateway_key"], {})
            if not info:
                info = {"product": m.get("product_id", ""), "device": m.get("device_id", "")}
            if info:
                all_products.add(info["product"])
                all_devices.setdefault(info["product"], set()).add(info["device"])

    VIRTUAL_PRODUCTS = sorted(p for p in all_products if p)
    VIRTUAL_DEVICES = {k: v for k, v in all_devices.items() if k}


def refresh_routing(force: bool = False):
    """从 SQLite 重新加载路由表. 返回 True 表示有变化."""
    global UP_ROUTING
    try:
        new_routing = load_routing()
    except Exception as e:
        print(f"[Bridge] 刷新路由表失败: {e}")
        return False

    with _routing_lock:
        old_keys = set(UP_ROUTING.keys())
        new_keys = set(new_routing.keys())
        changed = force or old_keys != new_keys or any(
            UP_ROUTING.get(k) != v for k, v in new_routing.items()
        )
        if changed:
            UP_ROUTING = new_routing
            _rebuild_all(new_routing)
            print(f"[Bridge] 路由表已刷新 ({len(new_routing)} 个 key)")
        return changed


def _start_hot_reload():
    """后台线程: 每 5 秒从 SQLite 刷新路由表"""
    def worker():
        print("[Bridge] hot-reload thread started (5s interval)")
        while True:
            time.sleep(5)
            try:
                changed = refresh_routing()
                if changed:
                    print(f"[Bridge] hot-reload: routing changed, now {len(UP_ROUTING)} keys")
                # else: print("[Bridge] hot-reload: no change")  # too noisy
            except Exception as e:
                print(f"[Bridge] hot-reload ERROR: {e}")
    t = threading.Thread(target=worker, daemon=True, name="routing-refresh")
    t.start()


# ============================================================
# 主题构造
# ============================================================
def t(base, product, device, suffix):
    """{base}/{product}/{device}/{suffix}"""
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
# ============================================================
_msg_map_lock = threading.Lock()
_msg_map = {}


def _next_bridge_id():
    return f"bridge-{int(time.time()*1000) % 1000000000}-{threading.get_ident() % 1000}"


def _store_reply_mapping(origin_product, origin_device, reply_key, bridge_msg_id, origin_msg_id):
    now = time.time()
    with _msg_map_lock:
        stale = [k for k, v in _msg_map.items() if now - v["ts"] > 30]
        for k in stale:
            del _msg_map[k]
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

    with _routing_lock:
        routing = dict(UP_ROUTING)

    by_virtual = {}
    for gw_key, value in props.items():
        # 同步写入 device_status 缓存 (供 Web 实物控制台读取)
        try:
            update_device_status(gw_key, value)
        except Exception as e:
            print(f"  ! device_status 写入失败 {gw_key}: {e}")

        info = routing.get(gw_key)
        if not info:
            continue
        vkey = (info["product"], info["device"])
        by_virtual.setdefault(vkey, {})[info["property"]] = value

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

    with _routing_lock:
        down = dict(DOWN_ROUTING)

    gw_props = {}
    for vprop, vval in props.items():
        gw_key = down.get((product, device, vprop))
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

    if fid == "write":
        handle_virtual_write(product, device, {
            "messageId": origin_mid,
            "timestamp": ts,
            "properties": inputs,
        })
        return

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
    """网关 reply → 路由回虚拟设备"""
    bridge_mid = payload.get("messageId", "")
    ts = payload.get("timestamp", int(time.time() * 1000))
    entry = _get_reply_target(bridge_mid)
    if not entry:
        print(f"  ? 网关 {reply_key} 无映射: {bridge_mid}")
        return

    origin_payload = dict(payload)
    origin_payload["messageId"] = entry["origin_msg_id"]

    reply_topic = virtual_topic(entry["origin_product"], entry["origin_device"], entry["reply_key"])
    _BRIDGE_PUBLISHER.publish(reply_topic, json.dumps(origin_payload), qos=1)
    print(f"  → gateway {reply_key} → {entry['origin_product']}/{entry['origin_device']} {entry['reply_key']}")


# ============================================================
# MQTT 回调
# ============================================================
def on_connect(client, userdata, flags, rc):
    if rc != 0:
        print(f"[Bridge] 连接失败 rc={rc}")
        return
    print(f"[Bridge] 已连接 {MQTT_HOST}:{MQTT_PORT}")

    client.subscribe(f"{GATEWAY_PRODUCT}/{GATEWAY_DEVICE}/#", qos=1)
    print(f"  订阅网关: {GATEWAY_PRODUCT}/{GATEWAY_DEVICE}/#")

    # 订阅所有虚拟产品的下行消息
    with _routing_lock:
        vd = dict(VIRTUAL_DEVICES)
    for product, devices in vd.items():
        for device in devices:
            suffixes = ["properties/write", "properties/read", "function/invoke"]
            for suffix in suffixes:
                topic = virtual_topic(product, device, suffix)
                client.subscribe(topic, qos=1)
        print(f"  订阅虚拟下行: {product} ({len(devices)} 设备)")


def on_message(client, userdata, msg):
    raw = msg.payload.decode() if msg.payload else ""
    t = msg.topic
    print(f"[Bridge RAW] {t} -> {raw[:80]}")
    if not raw:
        return
    try:
        payload = json.loads(raw)
    except Exception as e:
        print(f"[Bridge] 无法解析消息: topic={t[:60]} payload={raw[:80]} err={e}")
        return

    gateway_prefix = f"{GATEWAY_PRODUCT}/{GATEWAY_DEVICE}/"
    if t.startswith(gateway_prefix):
        handle_gateway_message(t, payload)
    else:
        handle_virtual_message(t, payload)


def handle_gateway_message(topic, payload):
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
    elif suffix == "properties/write":
        # Gateway DOWNLINK write - check if all relay keys are allowed
        # This catches JetLinks/EMQX rules that bypass Bridge
        _check_gateway_downlink_write(payload)
    elif suffix == "function/invoke":
        _check_gateway_downlink_invoke(payload)


def _check_gateway_downlink_write(payload):
    """拦截 JetLinks 绕过 Bridge 直接发到 gateway 的 write 消息.
    如果 payload 里的 relay* key 全部不在 UP_ROUTING 里(被禁用), 就丢弃.
    """
    props = payload.get("properties", {})
    if not props:
        return

    with _routing_lock:
        routing = dict(UP_ROUTING)

    # 找出 payload 里所有 relay* key
    relay_keys_in_payload = [k for k in props if k.startswith("relay")]
    if not relay_keys_in_payload:
        return  # 没有 relay key, 不拦截

    # 检查每个 relay key 是否在启用的路由里
    blocked = [k for k in relay_keys_in_payload if k not in routing]
    allowed = [k for k in relay_keys_in_payload if k in routing]

    if blocked and not allowed:
        # 所有 relay key 都被禁用 → 丢弃整条消息
        print(f"  🚫 拦截绕过 Bridge 的 write (relay 全部被禁用): {props}")
        return
    elif blocked and allowed:
        # 部分被禁用 → 去掉被禁用的 key, 让 ESP32 执行允许的
        filtered = {k: v for k, v in props.items() if k in routing}
        print(f"  ⚠️ 绕过 Bridge 的 write, 过滤禁用 key: blocked={blocked} → 剩余 {filtered}")
        # 重发过滤后的消息
        new_payload = dict(payload)
        new_payload["properties"] = filtered
        _BRIDGE_PUBLISHER.publish(GATEWAY_TOPICS["write"], json.dumps(new_payload), qos=1)
        return

    # 所有 key 都允许 → 正常放行 (Bridge 自己发的也是这种情况)
    print(f"  ⚡ 绕过 Bridge 的 write, 放行 (all keys enabled): {props}")


def _check_gateway_downlink_invoke(payload):
    """类似 write, 检查 function/invoke 里的 relay key."""
    inputs = payload.get("inputs", {})
    if isinstance(inputs, list):
        inputs = {i.get("name"): i.get("value") for i in inputs if isinstance(i, dict)}
    if not inputs:
        return

    with _routing_lock:
        routing = dict(UP_ROUTING)

    relay_keys_in_payload = [k for k in inputs if k.startswith("relay")]
    if not relay_keys_in_payload:
        return

    blocked = [k for k in relay_keys_in_payload if k not in routing]
    allowed = [k for k in relay_keys_in_payload if k in routing]

    if blocked and not allowed:
        print(f"  🚫 拦截绕过 Bridge 的 invoke (relay 全部被禁用): {payload.get('functionId','')}")
    elif blocked:
        print(f"  ⚠️ 绕过 Bridge 的 invoke, 部分禁用: blocked={blocked}")


def handle_virtual_message(topic, payload):
    parts = topic.split("/")
    if len(parts) < 4:
        return
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
        bridge_mid = _next_bridge_id()
        bridge_payload = {
            "timestamp": payload.get("timestamp", int(time.time() * 1000)),
            "messageId": bridge_mid,
        }
        if "properties" in payload:
            bridge_payload["properties"] = payload["properties"]
        _store_reply_mapping(product, device, "read_reply", bridge_mid,
                             payload.get("messageId", bridge_mid))
        _BRIDGE_PUBLISHER.publish(GATEWAY_TOPICS["read"], json.dumps(bridge_payload), qos=1)
        print(f"  ↓ {product}/{device} read")


# ============================================================
# 主程序
# ============================================================
_BRIDGE_PUBLISHER = None


def main():
    global _BRIDGE_PUBLISHER

    parser = argparse.ArgumentParser(description="Day9 Gateway Bridge")
    parser.add_argument("--hot-reload", action="store_true",
                        help="每 5 秒自动从 SQLite 刷新路由表 (默认关闭)")
    args = parser.parse_args()

    # 确保数据库存在
    init_db()

    # 启动时加载路由表
    refresh_routing(force=True)

    print("=" * 60)
    print("Day9 Gateway Bridge (SQLite 动态路由)")
    print("=" * 60)
    print(f"网关产品: {GATEWAY_PRODUCT}/{GATEWAY_DEVICE}")
    print(f"MQTT: {MQTT_HOST}:{MQTT_PORT}")
    print(f"数据库: {os.path.abspath('db/iot_platform.db')}")
    print(f"热重载: {'开启 (5s)' if args.hot_reload else '关闭 (启动时加载一次)'}")
    print(f"虚拟产品 ({len(VIRTUAL_PRODUCTS)} 个): {', '.join(VIRTUAL_PRODUCTS)}")
    print(f"路由表 ({len(UP_ROUTING)} 个 key):")
    for gw_key, info in sorted(UP_ROUTING.items()):
        print(f"  {gw_key:15s} → {info['product']:12s}/{info['device']:10s} ({info['property']})")
    print("=" * 60)

    if args.hot_reload:
        _start_hot_reload()

    client = mqtt_client.Client(
        client_id=BRIDGE_CLIENT_ID,
        clean_session=True,
    )
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.on_connect = on_connect
    client.on_message = on_message
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
