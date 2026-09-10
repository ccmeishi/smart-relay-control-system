"""Day10.2 大屏 REST 接口 (前缀 /api).

7 个接口:
  GET  /overview              设备概览 + 在线率
  GET  /device-status         设备实时状态
  GET  /alarm-stats           告警统计
  GET  /alarms/recent         最近告警列表
  GET  /scene-rules           场景规则列表
  GET  /history/<key>         某采集点历史
  POST /devices/toggle        继电器控制 (下发 MQTT + 广播 WS)
"""
import json
import threading
import time

from flask import Blueprint, jsonify, request

from log_setup import logger
import db
from ws_hub import hub, EV_RELAY_CHANGED, EV_DEVICE_STATUS

bp = Blueprint("api", __name__)

RELAY_KEYS = ("relay1", "relay2", "relay3", "relay4")


# ============================================================
# MQTT 下发客户端 (大屏后端专用, 独立 client_id 避免踢掉 bridge)
# ============================================================
_mqtt_client = None
_mqtt_lock = threading.Lock()


def _get_mqtt_client():
    """惰性创建并连接 paho 客户端. 连不上返回 None (大屏仍可演示, 仅下发失败)."""
    global _mqtt_client
    if _mqtt_client is not None:
        return _mqtt_client
    try:
        import paho.mqtt.client as mqtt
        cfg = db.load_gateway_config()
        client = mqtt.Client(client_id=f"day102-dashboard-{int(time.time())}")
        if cfg["mqtt_user"]:
            client.username_pw_set(cfg["mqtt_user"], cfg["mqtt_pass"])
        client.connect(cfg["mqtt_host"], cfg["mqtt_port"], keepalive=60)
        client.loop_start()
        time.sleep(0.5)  # 等待连接建立
        _mqtt_client = client
        logger.info(f"[api] MQTT 下发客户端已连接 {cfg['mqtt_host']}:{cfg['mqtt_port']}")
        return _mqtt_client
    except Exception as e:
        logger.error(f"[api] MQTT 连接失败 (大屏可演示, 设备不下发): {e}")
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
        "messageId": f"dashboard-{int(time.time() * 1000)}",
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
# GET 接口
# ============================================================
@bp.get("/overview")
def overview():
    return jsonify(db.get_overview())


@bp.get("/device-status")
def device_status():
    status = db.get_device_status_all()
    # 拍平成 {key: value}
    flat = {k: v["value"] for k, v in status.items()}
    return jsonify(flat)


@bp.get("/alarm-stats")
def alarm_stats():
    stats = db.get_alarm_stats()
    # 额外提供 by_level 分组
    stats["by_level"] = {
        "info": stats.get("info", 0),
        "warning": stats.get("warning", 0),
        "critical": stats.get("critical", 0),
    }
    # P2-14: 今日新增告警数 (按 SQLite 当天日期筛选, 修复"今日告警"显示全量的问题)
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
    # 只返回大屏需要的字段
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


# ============================================================
# 告警操作接口 (P1-4: 大屏演示 ack/clear 流程)
# ============================================================
@bp.post("/alarms/<int:aid>/ack")
def alarm_ack(aid):
    """确认单条告警 (active → acknowledged)"""
    n = db.acknowledge_alarm(aid, username="dashboard")
    return jsonify({"ok": True, "affected": n})


@bp.post("/alarms/ack-all")
def alarm_ack_all():
    """一键确认所有 active 告警"""
    n = db.acknowledge_all_alarms(username="dashboard")
    return jsonify({"ok": True, "count": n})


@bp.post("/alarms/clear-all")
def alarm_clear_all():
    """一键清除所有告警 (active + acknowledged → cleared)"""
    n = db.clear_all_alarms()
    return jsonify({"ok": True, "count": n})


# ============================================================
# POST 接口: 继电器控制
# ============================================================
@bp.post("/devices/toggle")
def devices_toggle():
    body = request.get_json(silent=True) or {}
    key = str(body.get("key", "")).strip()
    value = str(body.get("value", "")).strip()

    # 1. 参数校验
    if key not in RELAY_KEYS:
        return jsonify({"ok": False, "error": f"非法继电器 key: {key}"}), 400
    if value not in ("0", "1"):
        return jsonify({"ok": False, "error": "value 必须为 0 或 1"}), 400

    # 2. 写 device_status 表 (历史由后台 watcher 统一检测变化并记录, 避免重复写)
    db.update_device_status(key, value)

    # 3. MQTT 下发 (失败不阻塞, 大屏本地状态仍更新)
    published = _publish_relay_write({key: int(value)})

    # 4. WebSocket 广播
    hub.broadcast(EV_RELAY_CHANGED, {"key": key, "value": value,
                                     "published": published})
    # 同时推一份全量状态, 保证大屏一致
    flat = {k: v["value"] for k, v in db.get_device_status_all().items()}
    hub.broadcast(EV_DEVICE_STATUS, flat)

    return jsonify({"ok": True, "key": key, "value": value,
                    "mqtt_published": published})
