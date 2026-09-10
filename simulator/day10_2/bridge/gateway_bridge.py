"""Day10.2 Gateway Bridge: ESP32 网关 ↔ 多虚拟设备 协议转换 + 场景联动 + 告警触发

[Day10.2 改动] 本文件从 day10/ 复制, 仅修改 db 导入路径:
  - db.py 位于 ../backend/db.py (Day10.2 独立库 day10_2/iot_platform.db)
  - 数据流向: Bridge 写 SQLite → Flask 后台轮询 → WebSocket 广播大屏
  其余路由/场景/告警逻辑与 day10 完全一致.

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

# [Day10.2 改动] 把 ../backend 目录加入 sys.path, 导入 Day10.2 独立 db.py
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(os.path.dirname(_HERE), "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from db import (
    init_db, load_routing, load_all_mappings, update_device_status,
    evaluate_scene_rules, create_alarm, ACTION_LABELS, LEVEL_LABELS,
)

from paho.mqtt import client as mqtt_client

# ============================================================
# 连接配置: 统一从 esp32_firmware/config.json 读取
# ============================================================
from db import load_gateway_config
_cfg = load_gateway_config()

MQTT_HOST = _cfg["mqtt_host"]
MQTT_PORT = _cfg["mqtt_port"]
MQTT_USER = _cfg["mqtt_user"]
MQTT_PASS = _cfg["mqtt_pass"]

GATEWAY_PRODUCT = _cfg["product_id"]
GATEWAY_DEVICE  = _cfg["device_id"]

BRIDGE_CLIENT_ID = "bridge-day102-v1"  # [Day10.2 改动] 唯一 client_id, 避免与 day10 bridge 互踢

# 继电器 key 列表 (用于 all_relay_off / all_relay_on 时构造 payload)
RELAY_KEYS = ["relay1", "relay2", "relay3", "relay4"]

# 告警通知 topic (Web 前端订阅此 topic 实时接收告警)
ALARM_NOTIFY_TOPIC = "/system/alarm/notify"

# ============================================================
# 场景动作目标互斥锁 (防止规则冲突: 高温断电关掉后被有人开灯重新打开)
# 字典: {relay_key: expire_epoch}  过期时间 = now + 触发该锁的规则的 cooldown_sec
# all_relay_off/all_relay_on 执行后锁定所有继电器
# set_relay 执行前检查目标 relay 是否被锁, 被锁则跳过
# ============================================================
_relay_locks = {}
_relay_locks_lock = threading.Lock()

# 告警级别优先级 (数值越小优先级越高)
_LEVEL_PRIORITY = {"critical": 0, "warning": 1, "info": 2}


def _lock_relay(target_relay: str, cooldown_sec: int):
    """锁定单个继电器 cooldown_sec 秒"""
    with _relay_locks_lock:
        _relay_locks[target_relay] = time.time() + cooldown_sec


def _lock_all_relays(cooldown_sec: int):
    """锁定全部继电器 cooldown_sec 秒 (all_relay_off/on 后调用)"""
    with _relay_locks_lock:
        expire = time.time() + cooldown_sec
        for k in RELAY_KEYS:
            _relay_locks[k] = expire


def _is_relay_locked(target_relay: str) -> bool:
    """检查继电器是否被锁 (锁过期则自动清除)"""
    now = time.time()
    with _relay_locks_lock:
        if target_relay in _relay_locks:
            if _relay_locks[target_relay] > now:
                return True
            else:
                del _relay_locks[target_relay]  # 过期, 清除
        return False


# ============================================================
# 动态路由表
# ============================================================
_routing_lock = threading.Lock()
UP_ROUTING = {}
DOWN_ROUTING = {}
VIRTUAL_PRODUCTS = []
VIRTUAL_DEVICES = {}


def _rebuild_all(routing: dict):
    global DOWN_ROUTING, VIRTUAL_PRODUCTS, VIRTUAL_DEVICES
    down = {}
    for gw_key, info in routing.items():
        key = (info["product"], info["device"], info["property"])
        down[key] = gw_key
    DOWN_ROUTING = down
    try:
        all_mappings = load_all_mappings()
    except Exception:
        all_mappings = []
    all_products = set()
    all_devices = {}
    for m in all_mappings:
        info = routing.get(m["gateway_key"])
        if not info:
            info = {"product": m.get("product_id", ""), "device": m.get("device_id", "")}
        if info:
            all_products.add(info.get("product", ""))
            all_devices.setdefault(info.get("product", ""), set()).add(info.get("device", ""))
    VIRTUAL_PRODUCTS = sorted(p for p in all_products if p)
    VIRTUAL_DEVICES = {k: v for k, v in all_devices.items() if k}


def refresh_routing(force: bool = False):
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
    def worker():
        print("[Bridge] hot-reload thread started (5s interval)")
        while True:
            time.sleep(5)
            try:
                changed = refresh_routing()
                if changed:
                    print(f"[Bridge] hot-reload: routing changed, now {len(UP_ROUTING)} keys")
            except Exception as e:
                print(f"[Bridge] hot-reload ERROR: {e}")
    t = threading.Thread(target=worker, daemon=True, name="routing-refresh")
    t.start()


# ============================================================
# 主题构造
# ============================================================
def _build_gateway_topics():
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
    return f"/{product}/{device}/{suffix}"


# ============================================================
# 消息 ID 映射
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
        return _msg_map.pop(bridge_msg_id, None)


# ============================================================
# Day10 新增: 场景动作执行器
# ============================================================
def execute_scene_actions(actions: list):
    """执行场景规则产生的动作列表 (带优先级排序 + 目标互斥锁).

    每个 action:
      {rule_id, rule_name, action_type, action_target, action_value,
       alarm_level, source_key, source_value, cooldown_sec}

    冲突解决策略:
      1. 先按 alarm_level 排序 (critical > warning > info), 高优先级先执行
      2. all_relay_off/on 执行后锁定全部继电器 cooldown_sec 秒
      3. set_relay 执行前检查目标是否被锁, 被锁则跳过并打日志
      4. send_alarm 仅产生告警, 不参与锁机制
    """
    if not actions:
        return

    # ---- 第1步: 按告警级别排序 (critical 优先) ----
    actions.sort(key=lambda a: _LEVEL_PRIORITY.get(a.get("alarm_level", "warning"), 99))

    for act in actions:
        rule_name = act.get("rule_name", "")
        action_type = act.get("action_type", "")
        action_label = ACTION_LABELS.get(action_type, action_type)
        level = act.get("alarm_level", "warning")
        level_label = LEVEL_LABELS.get(level, level)
        source_key = act.get("source_key", "")
        source_value = act.get("source_value", "")
        cooldown_sec = int(act.get("cooldown_sec", 60))

        print(f"[场景] 规则「{rule_name}」命中 ({source_key}={source_value}) "
              f"→ {action_label} [告警级别: {level_label}]")

        # ---- 第2步: 执行设备控制动作 + 锁检查 ----
        gw_props = None
        skipped = False

        if action_type == "set_relay":
            target = act.get("action_target", "")
            value = act.get("action_value", "0")
            try:
                val_int = 1 if int(float(value)) == 1 else 0
            except (ValueError, TypeError):
                val_int = 0
            if target:
                # 🔑 检查目标继电器是否被锁 (critical 规则的 all_off/on 会锁住)
                if _is_relay_locked(target):
                    print(f"  🚫 跳过: {target} 被高优先级规则锁定, 冷却中...")
                    skipped = True
                else:
                    gw_props = {target: val_int}
                    # set_relay 也锁自己, 防止同级别规则重复覆盖
                    _lock_relay(target, cooldown_sec)

        elif action_type == "all_relay_off":
            gw_props = {k: 0 for k in RELAY_KEYS}
            # 🔑 锁全部继电器 cooldown_sec 秒, 期间 info 级别 set_relay 不能覆盖
            _lock_all_relays(cooldown_sec)
            print(f"  🔒 锁定全部继电器 {cooldown_sec} 秒, 防止被低优先级规则覆盖")

        elif action_type == "all_relay_on":
            gw_props = {k: 1 for k in RELAY_KEYS}
            _lock_all_relays(cooldown_sec)
            print(f"  🔒 锁定全部继电器 {cooldown_sec} 秒, 防止被低优先级规则覆盖")

        # send_alarm: gw_props 保持 None, 仅产生告警

        if gw_props:
            payload = {
                "timestamp": int(time.time() * 1000),
                "messageId": f"scene-{act.get('rule_id')}-{int(time.time()*1000)}",
                "properties": gw_props,
            }
            try:
                _BRIDGE_PUBLISHER.publish(
                    GATEWAY_TOPICS["write"],
                    json.dumps(payload), qos=1
                )
                print(f"  ↓ 场景下发 write: {gw_props}")
            except Exception as e:
                print(f"  ! 场景下发失败: {e}")

        # ---- 第3步: 产生告警记录 + 发布 MQTT 通知 ----
        # (被跳过的动作也要记录告警, 说明规则命中但被冲突抑制)
        msg = f"规则「{rule_name}」触发: {source_key}={source_value}"
        if skipped:
            msg += f", 但被更高优先级规则锁定而跳过执行"
        elif gw_props:
            msg += f", 已执行 {action_label}"
        try:
            alarm_id = create_alarm(
                rule_id=act.get("rule_id"),
                rule_name=rule_name,
                source_key=source_key,
                source_value=source_value,
                level=level,
                message=msg,
            )
            # 发布告警通知 (Web 前端实时接收)
            notify_payload = {
                "alarm_id": alarm_id,
                "rule_name": rule_name,
                "source_key": source_key,
                "source_value": source_value,
                "level": level,
                "message": msg,
                "timestamp": int(time.time() * 1000),
            }
            _BRIDGE_PUBLISHER.publish(
                ALARM_NOTIFY_TOPIC,
                json.dumps(notify_payload, ensure_ascii=False),
                qos=1
            )
            print(f"  ⚠️ 产生告警 #{alarm_id} [{level_label}] {msg}")
        except Exception as e:
            print(f"  ! 告警记录写入失败: {e}")


# ============================================================
# 上行: 网关 → 虚拟设备 (新增场景规则评估)
# ============================================================
def handle_gateway_properties_report(payload):
    """处理网关的 properties/report, 按路由表拆分转发 + 评估场景规则"""
    props = payload.get("properties", {})
    ts = payload.get("timestamp", int(time.time() * 1000))
    bridge_mid = payload.get("messageId", _next_bridge_id())

    with _routing_lock:
        routing = dict(UP_ROUTING)

    by_virtual = {}
    for gw_key, value in props.items():
        # 同步写入 device_status 缓存
        try:
            update_device_status(gw_key, value)
        except Exception as e:
            print(f"  ! device_status 写入失败 {gw_key}: {e}")

        # 按路由表拆分转发
        info = routing.get(gw_key)
        if info:
            vkey = (info["product"], info["device"])
            by_virtual.setdefault(vkey, {})[info["property"]] = value

        # Day10 新增: 评估场景规则 (只对变化的 key)
        try:
            actions = evaluate_scene_rules(gw_key, value)
            if actions:
                execute_scene_actions(actions)
        except Exception as e:
            print(f"  ! 场景规则评估失败 {gw_key}: {e}")

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
    origin_mid = payload.get("messageId", _next_bridge_id())
    ts = payload.get("timestamp", int(time.time() * 1000))
    fid = payload.get("functionId", "")
    inputs = payload.get("inputs", payload.get("properties", {}))
    if isinstance(inputs, list):
        inputs = {i.get("name"): i.get("value") for i in inputs if isinstance(i, dict)}
    if fid == "write":
        handle_virtual_write(product, device, {
            "messageId": origin_mid, "timestamp": ts, "properties": inputs,
        })
        return
    bridge_mid = _next_bridge_id()
    bridge_payload = {
        "timestamp": ts, "messageId": bridge_mid,
        "functionId": fid, "inputs": inputs,
    }
    _store_reply_mapping(product, device, "invoke_reply", bridge_mid, origin_mid)
    _BRIDGE_PUBLISHER.publish(GATEWAY_TOPICS["invoke"], json.dumps(bridge_payload), qos=1)
    print(f"  ↓ {product}/{device} invoke {fid} {inputs}")


def handle_gateway_reply(reply_key, payload):
    bridge_mid = payload.get("messageId", "")
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
    with _routing_lock:
        vd = dict(VIRTUAL_DEVICES)
    for product, devices in vd.items():
        for device in devices:
            for suffix in ["properties/write", "properties/read", "function/invoke"]:
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
        _check_gateway_downlink_write(payload)
    elif suffix == "function/invoke":
        _check_gateway_downlink_invoke(payload)


def _check_gateway_downlink_write(payload):
    props = payload.get("properties", {})
    if not props:
        return
    with _routing_lock:
        routing = dict(UP_ROUTING)
    relay_keys_in_payload = [k for k in props if k.startswith("relay")]
    if not relay_keys_in_payload:
        return
    blocked = [k for k in relay_keys_in_payload if k not in routing]
    allowed = [k for k in relay_keys_in_payload if k in routing]
    if blocked and not allowed:
        print(f"  🚫 拦截绕过 Bridge 的 write (relay 全部被禁用): {props}")
        return
    elif blocked and allowed:
        filtered = {k: v for k, v in props.items() if k in routing}
        print(f"  ⚠️ 绕过 Bridge 的 write, 过滤禁用 key: blocked={blocked} → 剩余 {filtered}")
        new_payload = dict(payload)
        new_payload["properties"] = filtered
        _BRIDGE_PUBLISHER.publish(GATEWAY_TOPICS["write"], json.dumps(new_payload), qos=1)
        return
    print(f"  ⚡ 绕过 Bridge 的 write, 放行 (all keys enabled): {props}")


def _check_gateway_downlink_invoke(payload):
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
    if blocked and not any(k in routing for k in relay_keys_in_payload):
        print(f"  🚫 拦截绕过 Bridge 的 invoke (relay 全部被禁用): {payload.get('functionId','')}")


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
    parser = argparse.ArgumentParser(description="Day10 Gateway Bridge")
    parser.add_argument("--hot-reload", action="store_true",
                        help="每 5 秒自动从 SQLite 刷新路由表")
    args = parser.parse_args()

    init_db()
    refresh_routing(force=True)

    from db import list_scene_rules
    rules = list_scene_rules(enabled_only=True)

    print("=" * 60)
    print("Day10 Gateway Bridge (SQLite 动态路由 + 场景联动 + 告警)")
    print("=" * 60)
    print(f"网关产品: {GATEWAY_PRODUCT}/{GATEWAY_DEVICE}")
    print(f"MQTT: {MQTT_HOST}:{MQTT_PORT}")
    print(f"数据库: {os.path.abspath('db/iot_platform.db')}")
    print(f"热重载: {'开启 (5s)' if args.hot_reload else '关闭'}")
    print(f"虚拟产品 ({len(VIRTUAL_PRODUCTS)} 个): {', '.join(VIRTUAL_PRODUCTS)}")
    print(f"路由表 ({len(UP_ROUTING)} 个 key)")
    print(f"场景规则 ({len(rules)} 个启用):")
    for r in rules:
        print(f"  [{r['id']}] {r['name']:20s} "
              f"IF {r['trigger_key']} {r['trigger_operator']} {r['trigger_value']} "
              f"THEN {r['action_type']}({r['action_target']},{r['action_value']}) "
              f"[冷却 {r['cooldown_sec']}s]")
    print(f"告警通知 topic: {ALARM_NOTIFY_TOPIC}")
    print("=" * 60)

    if args.hot_reload:
        _start_hot_reload()

    client = mqtt_client.Client(client_id=BRIDGE_CLIENT_ID, clean_session=True)
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
