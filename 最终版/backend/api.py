"""整合版 REST 接口 (前缀 /api).

分两类:
  [免登录 · 大屏用]
    GET  /overview              设备概览 + 在线率
    GET  /device-status         设备实时状态
    GET  /alarm-stats           告警统计
    GET  /alarms/recent         最近告警列表
    GET  /scene-rules           场景规则列表
    GET  /history/<key>         某采集点历史
    POST /alarms/<id>/ack       确认单条告警
    POST /alarms/ack-all        一键确认
    POST /alarms/clear-all      一键清除
    POST /devices/toggle        继电器控制 (MQTT 下发 + WS 广播)

  [需登录 · 管理后台用]
    POST /auth/login            登录
    POST /auth/logout           登出
    GET  /auth/me               当前用户
    GET  /stats                 管理看板统计                  (login)
    GET  /devices               设备控制台数据                (login)
    POST /devices/all           一键全开/全关                  (admin)
    GET  /mappings              映射列表                       (login)
    POST /mappings              新增映射                       (admin)
    PUT  /mappings/<id>         更新映射                       (admin)
    DELETE /mappings/<id>       删除映射                       (admin)
    POST /mappings/<id>/toggle  启用/禁用切换                  (admin)
    GET  /users                 用户列表                       (admin)
    POST /users                 新增用户                       (admin)
    PUT  /users/<id>/role       改角色                         (admin)
    PUT  /users/<id>/password   重置密码                       (admin)
    DELETE /users/<id>          删除用户                       (admin)
    GET  /sessions              在线用户 + 登录历史            (admin)
    GET  /config-points         网关配置 (非 admin 密码脱敏)   (login)
    POST /config-points         保存网关配置                   (admin)
"""
import os
import json
import threading
import time
from functools import wraps

from flask import Blueprint, jsonify, request, session

from log_setup import logger
import db
from ws_hub import hub, EV_RELAY_CHANGED, EV_DEVICE_STATUS

bp = Blueprint("api", __name__)

RELAY_KEYS = ("relay1", "relay2", "relay3", "relay4")
SENSOR_KEYS = ("temperature", "humidity", "human", "smoke")
SENSOR_UNITS = {
    "temperature": "°C",
    "humidity": "%",
    "human": "(0无人/1有人)",
    "smoke": "(0-100)",
}


# ============================================================
# 鉴权装饰器 (返回 JSON 401/403, 非 redirect, 适配 SPA)
# ============================================================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"ok": False, "error": "未登录"}), 401
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return jsonify({"ok": False, "error": "未登录"}), 401
        if session["user"].get("role") != "admin":
            return jsonify({"ok": False, "error": "需要管理员权限"}), 403
        return f(*args, **kwargs)
    return wrapper


# ============================================================
# MQTT 下发客户端 (复用 day10_2 实现; 大屏/管理后台共用)
# ============================================================
_mqtt_client = None
_mqtt_lock = threading.Lock()


def _get_mqtt_client():
    """惰性创建并连接 paho 客户端. 连不上返回 None (功能降级, 不阻塞)."""
    global _mqtt_client
    if _mqtt_client is not None:
        return _mqtt_client
    try:
        import paho.mqtt.client as mqtt
        cfg = db.load_gateway_config()
        client = mqtt.Client(client_id=f"iot-api-{int(time.time())}")
        if cfg["mqtt_user"]:
            client.username_pw_set(cfg["mqtt_user"], cfg["mqtt_pass"])
        client.connect(cfg["mqtt_host"], cfg["mqtt_port"], keepalive=60)
        client.loop_start()
        time.sleep(0.5)
        _mqtt_client = client
        logger.info(f"[api] MQTT 下发客户端已连接 {cfg['mqtt_host']}:{cfg['mqtt_port']}")
        return _mqtt_client
    except Exception as e:
        logger.error(f"[api] MQTT 连接失败 (功能降级, 设备不下发): {e}")
        return None


def _publish_relay_write(props: dict) -> bool:
    """向网关下发 properties/write. 返回是否成功 publish."""
    client = _get_mqtt_client()
    if client is None:
        return False
    cfg = db.load_gateway_config()
    topic = f"{cfg['product_id']}/{cfg['device_id']}/properties/write"
    payload = {
        "timestamp": int(time.time() * 1000),
        "messageId": f"api-{int(time.time() * 1000)}",
        "properties": props,
    }
    try:
        client.publish(topic, json.dumps(payload), qos=1)
        logger.info(f"[api] ↓ MQTT 下发 {topic}: {props}")
        return True
    except Exception as e:
        logger.error(f"[api] MQTT 下发失败: {e}")
        return False


# ============================================================
# 免登录接口 (大屏)
# ============================================================
@bp.get("/overview")
def overview():
    return jsonify(db.get_overview())


@bp.get("/device-status")
def device_status():
    status = db.get_device_status_all()
    flat = {k: v["value"] for k, v in status.items()}
    return jsonify(flat)


@bp.get("/alarm-stats")
def alarm_stats():
    stats = db.get_alarm_stats()
    stats["by_level"] = {
        "info": stats.get("info", 0),
        "warning": stats.get("warning", 0),
        "critical": stats.get("critical", 0),
    }
    # 今日新增告警数 (按 SQLite 当天日期筛选)
    import sqlite3
    with sqlite3.connect(db.DB_PATH) as conn:
        today_row = conn.execute(
            "SELECT COUNT(*) as c FROM alarm_records "
            "WHERE triggered_at >= date('now', 'start of day')"
        ).fetchone()
    stats["today"] = today_row[0] if today_row else 0
    return jsonify(stats)


@bp.get("/alarms/recent")
def alarms_recent():
    limit = request.args.get("limit", default=10, type=int)
    limit = max(1, min(limit, 50))
    return jsonify(db.get_recent_alarms(limit))


@bp.get("/scene-rules")
def scene_rules():
    rules = db.list_scene_rules()
    out = [
        {
            "id": r["id"],
            "name": r["name"],
            "description": r.get("description", ""),
            "trigger_key": r["trigger_key"],
            "trigger_operator": r["trigger_operator"],
            "trigger_value": r["trigger_value"],
            "action_type": r["action_type"],
            "alarm_level": r["alarm_level"],
            "enabled": r["enabled"],
            "trigger_count": r["trigger_count"],
            "last_triggered": r["last_triggered"],
        }
        for r in rules
    ]
    return jsonify(out)


@bp.get("/history/<gateway_key>")
def history(gateway_key):
    minutes = request.args.get("minutes", default=30, type=int)
    minutes = max(1, min(minutes, 180))
    return jsonify(db.get_history(gateway_key, minutes))


@bp.post("/alarms/<int:aid>/ack")
def alarm_ack(aid):
    n = db.acknowledge_alarm(aid, username=session.get("user", {}).get("username", "dashboard"))
    return jsonify({"ok": True, "affected": n})


@bp.post("/alarms/ack-all")
def alarm_ack_all():
    n = db.acknowledge_all_alarms(username=session.get("user", {}).get("username", "dashboard"))
    return jsonify({"ok": True, "count": n})


@bp.post("/alarms/clear-all")
def alarm_clear_all():
    n = db.clear_all_alarms()
    return jsonify({"ok": True, "count": n})


@bp.post("/devices/toggle")
def devices_toggle():
    """继电器控制 (大屏点击): 写 device_status + MQTT 下发 + WS 广播."""
    body = request.get_json(silent=True) or {}
    key = str(body.get("key", "")).strip()
    value = str(body.get("value", "")).strip()

    if key not in RELAY_KEYS:
        return jsonify({"ok": False, "error": f"非法继电器 key: {key}"}), 400
    if value not in ("0", "1"):
        return jsonify({"ok": False, "error": "value 必须为 0 或 1"}), 400

    db.update_device_status(key, value)
    published = _publish_relay_write({key: int(value)})
    hub.broadcast(EV_RELAY_CHANGED, {"key": key, "value": value, "published": published})
    flat = {k: v["value"] for k, v in db.get_device_status_all().items()}
    hub.broadcast(EV_DEVICE_STATUS, flat)

    return jsonify({"ok": True, "key": key, "value": value,
                    "mqtt_published": published})


# ============================================================
# 鉴权接口
# ============================================================
@bp.post("/auth/login")
def auth_login():
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", "")).strip()
    password = str(body.get("password", "")).strip()
    user = db.authenticate(username, password)
    if not user:
        return jsonify({"ok": False, "error": "用户名或密码错误"}), 401
    ip = request.remote_addr or ""
    sid = db.start_session(user["id"], user["username"], ip)
    db.kick_user_sessions(user["id"], keep_session_id=sid)  # 踢掉旧会话
    session.permanent = True
    session["user"] = {
        "id": user["id"],
        "username": user["username"],
        "role": user["role"],
        "display_name": user["display_name"] or user["username"],
        "session_id": sid,
    }
    logger.info(f"[auth] 登录成功: {user['username']} (role={user['role']})")
    return jsonify({"ok": True, "user": session["user"]})


@bp.post("/auth/logout")
def auth_logout():
    sess = session.get("user")
    if sess and "session_id" in sess:
        try:
            db.end_session(sess["session_id"])
        except Exception:
            pass
    session.clear()
    return jsonify({"ok": True})


@bp.get("/auth/me")
def auth_me():
    return jsonify({"user": session.get("user")})  # 未登录时 user=None


# ============================================================
# 管理看板统计
# ============================================================
@bp.get("/stats")
@login_required
def stats():
    mappings = db.load_all_mappings()
    enabled = [m for m in mappings if m["enabled"]]
    products = {}
    for m in enabled:
        products.setdefault(m["product_id"], 0)
        products[m["product_id"]] += 1
    virtual_devices = set((m["product_id"], m["device_id"]) for m in enabled)
    return jsonify({
        "total_mappings": len(mappings),
        "enabled_count": len(enabled),
        "disabled_count": len(mappings) - len(enabled),
        "product_stats": products,
        "virtual_device_count": len(virtual_devices),
        "user_count": len(db.list_users()),
        "online_count": db.get_online_count(),
        "alarm_stats": db.get_alarm_stats(),
        "overview": db.get_overview(),
    })


# ============================================================
# 设备控制台
# ============================================================
@bp.get("/devices")
@login_required
def devices_console():
    mappings = {m["gateway_key"]: m for m in db.load_all_mappings()}
    status = db.get_device_status_all()

    relay_cards = []
    for k in RELAY_KEYS:
        m = mappings.get(k, {})
        st = status.get(k, {})
        val = st.get("value", "-")
        try:
            val_int = int(float(val))
        except (ValueError, TypeError):
            val_int = 0
        relay_cards.append({
            "key": k, "desc": m.get("description", ""),
            "product": m.get("product_id", ""), "device": m.get("device_id", ""),
            "enabled": m.get("enabled", 0), "value": val_int,
            "updated_at": st.get("updated_at", ""),
        })

    sensor_cards = []
    for k in SENSOR_KEYS:
        m = mappings.get(k, {})
        st = status.get(k, {})
        sensor_cards.append({
            "key": k, "desc": m.get("description", ""),
            "product": m.get("product_id", ""),
            "value": st.get("value", "暂无数据"),
            "unit": SENSOR_UNITS.get(k, ""),
            "updated_at": st.get("updated_at", ""),
        })
    return jsonify({"relay_cards": relay_cards, "sensor_cards": sensor_cards})


@bp.post("/devices/all")
@admin_required
def devices_all():
    """一键全开/全关."""
    body = request.get_json(silent=True) or {}
    action = str(body.get("action", "on")).strip()
    target_val = 1 if action == "on" else 0
    props = {k: target_val for k in RELAY_KEYS}
    published = _publish_relay_write(props)
    for k in RELAY_KEYS:
        db.update_device_status(k, str(target_val))
    flat = {k: v["value"] for k, v in db.get_device_status_all().items()}
    hub.broadcast(EV_DEVICE_STATUS, flat)
    return jsonify({"ok": True, "action": action, "mqtt_published": published})


# ============================================================
# 映射管理 CRUD
# ============================================================
@bp.get("/mappings")
@login_required
def mappings_list():
    return jsonify(db.load_all_mappings())


@bp.post("/mappings")
@admin_required
def mappings_add():
    body = request.get_json(silent=True) or {}
    try:
        db.add_mapping(
            gateway_key=body.get("gateway_key", "").strip(),
            product_id=body.get("product_id", "").strip(),
            device_id=body.get("device_id", "").strip(),
            property_name=body.get("property_name", "").strip(),
            description=body.get("description", "").strip(),
        )
        return jsonify({"ok": True}), 201
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.put("/mappings/<int:mid>")
@admin_required
def mappings_update(mid):
    body = request.get_json(silent=True) or {}
    try:
        db.update_mapping(
            mapping_id=mid,
            gateway_key=body.get("gateway_key"),
            product_id=body.get("product_id"),
            device_id=body.get("device_id"),
            property_name=body.get("property_name"),
            description=body.get("description"),
            enabled=body.get("enabled"),
        )
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.delete("/mappings/<int:mid>")
@admin_required
def mappings_delete(mid):
    db.delete_mapping(mid)
    return jsonify({"ok": True})


@bp.post("/mappings/<int:mid>/toggle")
@admin_required
def mappings_toggle(mid):
    mappings = db.load_all_mappings()
    target = [m for m in mappings if m["id"] == mid]
    if not target:
        return jsonify({"ok": False, "error": "映射不存在"}), 404
    new_state = 0 if target[0]["enabled"] else 1
    db.update_mapping(mid, enabled=new_state)
    return jsonify({"ok": True, "enabled": new_state})


# ============================================================
# 用户管理 (admin)
# ============================================================
@bp.get("/users")
@admin_required
def users_list():
    return jsonify(db.list_users())


@bp.post("/users")
@admin_required
def users_add():
    body = request.get_json(silent=True) or {}
    try:
        db.add_user(
            username=body.get("username", "").strip(),
            password=body.get("password", "").strip(),
            role=body.get("role", "user"),
            display_name=body.get("display_name", "").strip(),
        )
        return jsonify({"ok": True}), 201
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.put("/users/<int:uid>/role")
@admin_required
def users_role(uid):
    body = request.get_json(silent=True) or {}
    try:
        db.update_user_role(uid, body.get("role", "user"))
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.put("/users/<int:uid>/password")
@admin_required
def users_password(uid):
    body = request.get_json(silent=True) or {}
    try:
        db.reset_password(uid, body.get("password", "").strip())
        return jsonify({"ok": True})
    except ValueError as e:
        return jsonify({"ok": False, "error": str(e)}), 400


@bp.delete("/users/<int:uid>")
@admin_required
def users_delete(uid):
    if uid == session["user"]["id"]:
        return jsonify({"ok": False, "error": "不能删除当前登录的自己"}), 400
    db.delete_user(uid)
    return jsonify({"ok": True})


# ============================================================
# 在线用户 / 登录历史 (admin)
# ============================================================
@bp.get("/sessions")
@admin_required
def sessions_list():
    return jsonify({
        "online": db.list_online_users(),
        "recent": db.list_recent_sessions(limit=30),
        "online_count": db.get_online_count(),
    })


# ============================================================
# 网关配置 (config.json) 读写
# ============================================================
@bp.get("/config-points")
@login_required
def config_points_get():
    config_path = db.GATEWAY_CONFIG_PATH
    if not os.path.exists(config_path):
        return jsonify({"ok": False, "error": "config.json 不存在"}), 404
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
    except Exception as e:
        return jsonify({"ok": False, "error": f"读取失败: {e}"}), 500
    is_admin = session.get("user", {}).get("role") == "admin"
    if not is_admin:
        # 非 admin: 密码字段脱敏
        for key in ("wifi_pass", "mqtt_pass"):
            if config_data.get(key):
                config_data[key] = "******"
    return jsonify({"config": config_data, "is_admin": is_admin, "path": config_path})


@bp.post("/config-points")
@admin_required
def config_points_save():
    body = request.get_json(silent=True) or {}
    config_path = db.GATEWAY_CONFIG_PATH
    if not os.path.exists(config_path):
        return jsonify({"ok": False, "error": "config.json 不存在"}), 404
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        return jsonify({"ok": False, "error": f"读取失败: {e}"}), 500

    try:
        config["wifi_ssid"] = body.get("wifi_ssid", config.get("wifi_ssid", ""))
        if body.get("wifi_pass") and body["wifi_pass"] != "******":
            config["wifi_pass"] = body["wifi_pass"]
        config["mqtt_host"] = body.get("mqtt_host", config.get("mqtt_host", ""))
        if body.get("mqtt_pass") and body["mqtt_pass"] != "******":
            config["mqtt_pass"] = body["mqtt_pass"]
        try:
            config["mqtt_port"] = int(body.get("mqtt_port", config.get("mqtt_port", 1883)))
        except (ValueError, TypeError):
            pass
        config["device_id"] = body.get("device_id", config.get("device_id", ""))
        config["product_id"] = body.get("product_id", config.get("product_id", ""))
        # 采集点配置 (前端提交完整 modbus_slaves 结构)
        if "modbus_slaves" in body:
            config["modbus_slaves"] = body["modbus_slaves"]
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        return jsonify({"ok": True, "msg": "配置已保存, ESP32 需重启生效"})
    except Exception as e:
        return jsonify({"ok": False, "error": f"保存失败: {e}"}), 500
