"""Day10 IoT 管理平台 - Flask Web 后端

Day9 基础上新增:
  - 场景规则管理 (CRUD + 启用/禁用) /scenes
  - 告警记录管理 (查看/确认/清除) /alarms
  - 看板新增告警统计 + 场景规则统计
  - 手动触发告警 (测试用)

运行:
  python web/app.py
  浏览器打开 http://127.0.0.1:8081
  默认账号: admin / admin123  或  user / user123
"""
import os
import sys
import json
import time
import re
import threading
from functools import wraps

# 把 day10/ 目录加入 sys.path, 让 db.py 可被导入
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from db import (
    init_db, load_all_mappings, add_mapping, update_mapping, delete_mapping,
    authenticate, list_users, add_user, update_user_role, delete_user, reset_password,
    start_session, kick_user_sessions, end_session, touch_session, list_online_users,
    list_recent_sessions, get_online_count,
    get_device_status_all, load_gateway_config,
    # Day10 新增
    list_scene_rules, add_scene_rule, update_scene_rule, delete_scene_rule,
    list_alarms, list_active_alarms, acknowledge_alarm, clear_alarm,
    acknowledge_all_alarms, clear_all_alarms, create_alarm, get_alarm_stats,
    get_scene_rule_stats,
    ACTION_LABELS, LEVEL_LABELS, LEVEL_COLORS,
    VALID_OPERATORS, VALID_LEVELS, VALID_ACTIONS,
    _RE_USER, _RE_PASS,
)

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

app = Flask(__name__, static_folder=os.path.join(_HERE, "static"))
app.secret_key = "day10-iot-platform-secret-key-change-in-production"


# ============================================================
# MQTT 下发 (实物控制台用)
# ============================================================
_MQTT_LOCK = threading.Lock()
_MQTT_CLIENT = None

def _get_mqtt():
    global _MQTT_CLIENT
    if _MQTT_CLIENT is not None:
        return _MQTT_CLIENT
    try:
        from paho.mqtt import client as mqtt_client
    except ImportError:
        return None
    client = mqtt_client.Client(client_id="web-admin-day10", clean_session=True)
    gw_cfg = load_gateway_config()
    client.username_pw_set(gw_cfg["mqtt_user"], gw_cfg["mqtt_pass"])
    try:
        client.connect(gw_cfg["mqtt_host"], gw_cfg["mqtt_port"], keepalive=30)
        client.loop_start()
        _MQTT_CLIENT = client
        print(f"[Web] MQTT 客户端已连接 {gw_cfg['mqtt_host']}:{gw_cfg['mqtt_port']}")
    except Exception as e:
        print(f"[Web] MQTT 连接失败: {e}")
        return None
    return _MQTT_CLIENT


# ============================================================
# 鉴权装饰器
# ============================================================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "user" not in session:
            return redirect(url_for("login"))
        if session["user"]["role"] != "admin":
            flash("此操作需要管理员权限", "error")
            return redirect(url_for("dashboard"))
        return f(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_user():
    return {"current_user": session.get("user")}


@app.before_request
def _heartbeat_session():
    sess = session.get("user")
    if sess and "session_id" in sess:
        try:
            touch_session(sess["session_id"])
        except Exception:
            pass


# ============================================================
# 登录 / 登出
# ============================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        user = authenticate(username, password)
        if user:
            ip = request.remote_addr or ""
            sid = start_session(user["id"], user["username"], ip)
            kick_user_sessions(user["id"], keep_session_id=sid)
            session["user"] = {
                "id": user["id"],
                "username": user["username"],
                "role": user["role"],
                "display_name": user["display_name"] or user["username"],
                "session_id": sid,
            }
            flash(f"欢迎回来, {session['user']['display_name']}!", "success")
            return redirect(url_for("dashboard"))
        else:
            flash("用户名或密码错误", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    sess = session.get("user")
    if sess and "session_id" in sess:
        try:
            end_session(sess["session_id"])
        except Exception:
            pass
    session.clear()
    flash("已退出登录", "info")
    return redirect(url_for("login"))


# ============================================================
# 看板 (新增告警/场景统计)
# ============================================================
@app.route("/")
@app.route("/dashboard")
@login_required
def dashboard():
    mappings = load_all_mappings()
    enabled = [m for m in mappings if m["enabled"]]
    total_mappings = len(mappings)
    enabled_count = len(enabled)
    disabled_count = total_mappings - enabled_count
    products = {}
    for m in enabled:
        products.setdefault(m["product_id"], 0)
        products[m["product_id"]] += 1
    gateway_keys = {}
    for m in enabled:
        gateway_keys.setdefault(m["gateway_key"], m["description"] or m["gateway_key"])
    virtual_devices = set()
    for m in enabled:
        virtual_devices.add((m["product_id"], m["device_id"]))
    user_count = len(list_users())
    online_count = get_online_count()
    # Day10 新增统计
    alarm_stats = get_alarm_stats()
    scene_stats = get_scene_rule_stats()
    return render_template(
        "dashboard.html",
        total_mappings=total_mappings,
        enabled_count=enabled_count,
        disabled_count=disabled_count,
        product_stats=products,
        virtual_device_count=len(virtual_devices),
        gateway_keys=gateway_keys,
        user_count=user_count,
        online_count=online_count,
        alarm_stats=alarm_stats,
        scene_stats=scene_stats,
        level_labels=LEVEL_LABELS,
    )


# ============================================================
# 映射管理
# ============================================================
@app.route("/mappings")
@login_required
def mappings_list():
    mappings = load_all_mappings()
    return render_template("mappings.html", mappings=mappings)


@app.route("/mappings/add", methods=["POST"])
@admin_required
def mappings_add():
    try:
        add_mapping(
            gateway_key=request.form["gateway_key"].strip(),
            product_id=request.form["product_id"].strip(),
            device_id=request.form["device_id"].strip(),
            property_name=request.form["property_name"].strip(),
            description=request.form.get("description", "").strip(),
        )
        flash("映射添加成功", "success")
    except Exception as e:
        flash(f"添加失败: {e}", "error")
    return redirect(url_for("mappings_list"))


@app.route("/mappings/<int:mid>/edit", methods=["POST"])
@admin_required
def mappings_edit(mid):
    try:
        update_mapping(
            mapping_id=mid,
            gateway_key=request.form["gateway_key"].strip(),
            product_id=request.form["product_id"].strip(),
            device_id=request.form["device_id"].strip(),
            property_name=request.form["property_name"].strip(),
            description=request.form.get("description", "").strip(),
            enabled=(request.form.get("enabled") == "on"),
        )
        flash("映射更新成功", "success")
    except Exception as e:
        flash(f"更新失败: {e}", "error")
    return redirect(url_for("mappings_list"))


@app.route("/mappings/<int:mid>/delete", methods=["POST"])
@admin_required
def mappings_delete(mid):
    try:
        delete_mapping(mid)
        flash("映射已删除", "success")
    except Exception as e:
        flash(f"删除失败: {e}", "error")
    return redirect(url_for("mappings_list"))


@app.route("/mappings/<int:mid>/toggle", methods=["POST"])
@admin_required
def mappings_toggle(mid):
    try:
        mappings = load_all_mappings()
        target = [m for m in mappings if m["id"] == mid]
        if not target:
            flash("映射不存在", "error")
            return redirect(url_for("mappings_list"))
        new_state = 0 if target[0]["enabled"] else 1
        update_mapping(mid, enabled=new_state)
        flash(f"映射已{'禁用' if not new_state else '启用'}", "success")
    except Exception as e:
        flash(f"操作失败: {e}", "error")
    return redirect(url_for("mappings_list"))


@app.route("/api/routing")
@login_required
def api_routing():
    mappings = load_all_mappings()
    return jsonify({"count": len(mappings), "items": mappings})


# ============================================================
# 用户管理 (admin 专属)
# ============================================================
@app.route("/users")
@admin_required
def users_list():
    users = list_users()
    return render_template("users.html", users=users)


@app.route("/users/add", methods=["POST"])
@admin_required
def users_add():
    try:
        username = request.form["username"].strip()
        password = request.form["password"].strip()
        role = request.form.get("role", "user")
        display_name = request.form.get("display_name", "").strip()
        if not _RE_USER.match(username):
            flash("用户名格式不合法 (仅字母数字下划线, 3-20 位)", "error")
            return redirect(url_for("users_list"))
        if not _RE_PASS.match(password):
            flash("密码格式不合法 (至少 6 位可打印 ASCII)", "error")
            return redirect(url_for("users_list"))
        if role not in ("admin", "user"):
            flash("角色必须是 admin 或 user", "error")
            return redirect(url_for("users_list"))
        add_user(username=username, password=password, role=role, display_name=display_name)
        flash("用户创建成功", "success")
    except Exception as e:
        flash(f"创建失败: {e}", "error")
    return redirect(url_for("users_list"))


@app.route("/users/<int:uid>/role", methods=["POST"])
@admin_required
def users_role(uid):
    try:
        role = request.form.get("role", "user")
        if role not in ("admin", "user"):
            flash("角色必须是 admin 或 user", "error")
            return redirect(url_for("users_list"))
        update_user_role(uid, role)
        flash("角色已更新", "success")
    except Exception as e:
        flash(f"更新失败: {e}", "error")
    return redirect(url_for("users_list"))


@app.route("/users/<int:uid>/password", methods=["POST"])
@admin_required
def users_password(uid):
    try:
        password = request.form.get("password", "").strip()
        if not _RE_PASS.match(password):
            flash("密码格式不合法 (至少 6 位可打印 ASCII)", "error")
            return redirect(url_for("users_list"))
        reset_password(uid, password)
        flash("密码已重置", "success")
    except Exception as e:
        flash(f"重置失败: {e}", "error")
    return redirect(url_for("users_list"))


@app.route("/users/<int:uid>/delete", methods=["POST"])
@admin_required
def users_delete(uid):
    if uid == session["user"]["id"]:
        flash("不能删除当前登录的自己", "error")
        return redirect(url_for("users_list"))
    try:
        delete_user(uid)
        flash("用户已删除", "success")
    except Exception as e:
        flash(f"删除失败: {e}", "error")
    return redirect(url_for("users_list"))


# ============================================================
# 实物控制台
# ============================================================
GATEWAY_PRODUCT = "relay-cc"
GATEWAY_DEVICE  = "relaycc"
RELAY_KEYS = ["relay1", "relay2", "relay3", "relay4"]
SENSOR_KEYS = ["temperature", "humidity", "human", "smoke"]
SENSOR_UNITS = {
    "temperature": "C",
    "humidity": "%",
    "human": "(0无人/1有人)",
    "smoke": "(0-100)",
}


@app.route("/devices")
@login_required
def devices_console():
    config_path = os.path.join(_PARENT, "esp32_firmware", "config.json")
    modbus_points = []
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            for slave in cfg.get("modbus_slaves", []):
                for pt in slave.get("points", []):
                    modbus_points.append({
                        "slave_id": slave.get("unit_id", slave.get("slave_id", "")),
                        "addr": pt.get("addr", ""),
                        "key": pt.get("key", ""),
                        "period_ms": pt.get("period_ms", ""),
                        "type": pt.get("type", ""),
                        "scale": pt.get("scale", ""),
                        "count": pt.get("count", 1),
                    })
        except Exception as e:
            print(f"[Web] 读取 config.json 失败: {e}")
    status = get_device_status_all()
    mappings = {m["gateway_key"]: m for m in load_all_mappings()}
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
    return render_template("devices.html", relay_cards=relay_cards,
                           sensor_cards=sensor_cards, modbus_points=modbus_points)


@app.route("/devices/toggle", methods=["POST"])
@admin_required
def devices_toggle():
    key = request.form.get("key", "").strip()
    value = request.form.get("value", "0").strip()
    if key not in RELAY_KEYS:
        return jsonify({"ok": False, "msg": f"无效的继电器 key: {key}"}), 400
    try:
        val_int = 1 if int(value) == 1 else 0
    except (ValueError, TypeError):
        val_int = 0
    mappings = {m["gateway_key"]: m for m in load_all_mappings()}
    m = mappings.get(key)
    if not m:
        return jsonify({"ok": False, "msg": f"映射 {key} 不存在"}), 404
    if not m.get("enabled"):
        return jsonify({"ok": False, "msg": f"映射 {key} 已禁用, 无法控制"}), 403
    client = _get_mqtt()
    if not client:
        return jsonify({"ok": False, "msg": "MQTT 客户端未连接"}), 500
    topic = f"{GATEWAY_PRODUCT}/{GATEWAY_DEVICE}/properties/write"
    payload = {
        "timestamp": int(time.time() * 1000),
        "messageId": f"web-{int(time.time()*1000)}",
        "properties": {key: val_int},
    }
    try:
        info = client.publish(topic, json.dumps(payload), qos=1)
        return jsonify({"ok": True, "msg": f"已下发 {key}={'开' if val_int else '关'}"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"下发失败: {e}"}), 500


@app.route("/devices/all", methods=["POST"])
@admin_required
def devices_all():
    action = request.form.get("action", "on")
    target_val = 1 if action == "on" else 0
    client = _get_mqtt()
    if not client:
        return jsonify({"ok": False, "msg": "MQTT 客户端未连接"}), 500
    mappings = {m["gateway_key"]: m for m in load_all_mappings()}
    props = {}
    for k in RELAY_KEYS:
        m = mappings.get(k)
        if m and m.get("enabled"):
            props[k] = target_val
    if not props:
        return jsonify({"ok": False, "msg": "无启用的继电器映射"}), 400
    topic = f"{GATEWAY_PRODUCT}/{GATEWAY_DEVICE}/properties/write"
    payload = {
        "timestamp": int(time.time() * 1000),
        "messageId": f"web-all-{int(time.time()*1000)}",
        "properties": props,
    }
    try:
        client.publish(topic, json.dumps(payload), qos=1)
        return jsonify({"ok": True, "msg": f"已下发{'全开' if target_val else '全关'}: {props}"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"下发失败: {e}"}), 500


@app.route("/api/device-status")
@login_required
def api_device_status():
    return jsonify(get_device_status_all())


# ============================================================
# 在线用户 / 登录历史
# ============================================================
@app.route("/sessions")
@admin_required
def sessions_list():
    online = list_online_users()
    history = list_recent_sessions(limit=30)
    return render_template("sessions.html", online=online, history=history)


# ============================================================
# 采集点配置
# ============================================================
@app.route("/config-points")
@login_required
def config_points():
    config_path = os.path.join(_PARENT, "esp32_firmware", "config.json")
    config_data = None
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = json.load(f)
        except Exception as e:
            flash(f"读取 config.json 失败: {e}", "error")
    is_admin = current_user_is_admin()
    safe_json = None
    if config_data and not is_admin:
        import copy
        safe_cfg = copy.deepcopy(config_data)
        for key in ("wifi_pass", "mqtt_pass"):
            if key in safe_cfg and safe_cfg[key]:
                safe_cfg[key] = "******"
        safe_json = json.dumps(safe_cfg, indent=2, ensure_ascii=False)
    elif config_data:
        safe_json = json.dumps(config_data, indent=2, ensure_ascii=False)
    return render_template("config_points.html", config=config_data,
                           config_path=config_path, is_admin=is_admin, safe_json=safe_json)


def current_user_is_admin():
    sess = session.get("user")
    return sess is not None and sess.get("role") == "admin"


@app.route("/config-points/save", methods=["POST"])
@admin_required
def config_points_save():
    config_path = os.path.join(_PARENT, "esp32_firmware", "config.json")
    if not os.path.exists(config_path):
        flash("config.json 文件不存在, 无法保存", "error")
        return redirect(url_for("config_points"))
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        flash(f"读取 config.json 失败: {e}", "error")
        return redirect(url_for("config_points"))
    try:
        config["wifi_ssid"] = request.form.get("wifi_ssid", config.get("wifi_ssid", ""))
        config["wifi_pass"] = request.form.get("wifi_pass", config.get("wifi_pass", ""))
        config["mqtt_host"] = request.form.get("mqtt_host", config.get("mqtt_host", ""))
        mqtt_port_str = request.form.get("mqtt_port", str(config.get("mqtt_port", 1883)))
        try:
            config["mqtt_port"] = int(mqtt_port_str)
        except ValueError:
            config["mqtt_port"] = config.get("mqtt_port", 1883)
        config["device_id"] = request.form.get("device_id", config.get("device_id", ""))
        config["product_id"] = request.form.get("product_id", config.get("product_id", ""))
        modbus_slaves = config.get("modbus_slaves", [])
        _FIELD_RE = re.compile(r'^slave_(\d+)_(addr|key|period_ms|type|scale|count|write)_(\d+)$')
        submitted = {}
        for key, value in request.form.items():
            m = _FIELD_RE.match(key)
            if not m:
                continue
            s_idx = int(m.group(1))
            field = m.group(2)
            p_idx = int(m.group(3))
            submitted.setdefault(s_idx, {}).setdefault(p_idx, {})[field] = value
        for s_idx, points_dict in submitted.items():
            if s_idx >= len(modbus_slaves):
                continue
            new_points = []
            for p_idx, fields in sorted(points_dict.items()):
                point = {}
                addr_str = fields.get("addr", "0")
                try:
                    addr_str = addr_str.strip()
                    if addr_str.lower().startswith("0x"):
                        point["addr"] = int(addr_str, 16)
                    else:
                        point["addr"] = int(addr_str)
                except ValueError:
                    point["addr"] = 0
                point["key"] = fields.get("key", "").strip()
                try:
                    point["period_ms"] = max(500, int(fields.get("period_ms", 3000)))
                except ValueError:
                    point["period_ms"] = 3000
                point["type"] = fields.get("type", "uint16").strip()
                try:
                    point["scale"] = float(fields.get("scale", 1))
                except ValueError:
                    point["scale"] = 1.0
                try:
                    point["count"] = max(1, int(fields.get("count", 1)))
                except ValueError:
                    point["count"] = 1
                point["write"] = fields.get("write") == "on"
                if point["key"]:
                    new_points.append(point)
            modbus_slaves[s_idx]["points"] = new_points
        config["modbus_slaves"] = modbus_slaves
        backup_path = config_path + ".bak"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                old = f.read()
            with open(backup_path, "w", encoding="utf-8") as f:
                f.write(old)
        except Exception:
            pass
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        flash("采集点配置已保存! ESP32 设备需要重启后生效", "success")
    except Exception as e:
        flash(f"保存失败: {e}", "error")
    return redirect(url_for("config_points"))


# ============================================================
# Day10 新增: 场景规则管理
# ============================================================
@app.route("/scenes")
@login_required
def scenes_list():
    rules = list_scene_rules()
    # 获取采集点列表 (供新增/编辑表单的下拉选择)
    mappings = load_all_mappings()
    gateway_keys = sorted(set(m["gateway_key"] for m in mappings))
    return render_template("scenes.html", rules=rules, gateway_keys=gateway_keys,
                           action_labels=ACTION_LABELS, level_labels=LEVEL_LABELS,
                           level_colors=LEVEL_COLORS,
                           operators=VALID_OPERATORS, levels=VALID_LEVELS,
                           actions=VALID_ACTIONS, relay_keys=RELAY_KEYS)


@app.route("/scenes/add", methods=["POST"])
@admin_required
def scenes_add():
    try:
        add_scene_rule(
            name=request.form["name"].strip(),
            trigger_key=request.form["trigger_key"].strip(),
            trigger_operator=request.form["trigger_operator"].strip(),
            trigger_value=request.form["trigger_value"].strip(),
            action_type=request.form["action_type"].strip(),
            action_target=request.form.get("action_target", "").strip(),
            action_value=request.form.get("action_value", "").strip(),
            alarm_level=request.form.get("alarm_level", "warning").strip(),
            cooldown_sec=request.form.get("cooldown_sec", "60").strip(),
            description=request.form.get("description", "").strip(),
        )
        flash("场景规则添加成功", "success")
    except Exception as e:
        flash(f"添加失败: {e}", "error")
    return redirect(url_for("scenes_list"))


@app.route("/scenes/<int:rid>/edit", methods=["POST"])
@admin_required
def scenes_edit(rid):
    try:
        update_scene_rule(rid,
            name=request.form["name"].strip(),
            description=request.form.get("description", "").strip(),
            trigger_key=request.form["trigger_key"].strip(),
            trigger_operator=request.form["trigger_operator"].strip(),
            trigger_value=request.form["trigger_value"].strip(),
            action_type=request.form["action_type"].strip(),
            action_target=request.form.get("action_target", "").strip(),
            action_value=request.form.get("action_value", "").strip(),
            alarm_level=request.form.get("alarm_level", "warning").strip(),
            cooldown_sec=request.form.get("cooldown_sec", "60").strip(),
            enabled=(request.form.get("enabled") == "on"),
        )
        flash("场景规则更新成功", "success")
    except Exception as e:
        flash(f"更新失败: {e}", "error")
    return redirect(url_for("scenes_list"))


@app.route("/scenes/<int:rid>/delete", methods=["POST"])
@admin_required
def scenes_delete(rid):
    try:
        delete_scene_rule(rid)
        flash("场景规则已删除", "success")
    except Exception as e:
        flash(f"删除失败: {e}", "error")
    return redirect(url_for("scenes_list"))


@app.route("/scenes/<int:rid>/toggle", methods=["POST"])
@admin_required
def scenes_toggle(rid):
    try:
        rules = list_scene_rules()
        target = [r for r in rules if r["id"] == rid]
        if not target:
            flash("规则不存在", "error")
            return redirect(url_for("scenes_list"))
        new_state = 0 if target[0]["enabled"] else 1
        update_scene_rule(rid, enabled=new_state)
        flash(f"规则已{'禁用' if not new_state else '启用'}", "success")
    except Exception as e:
        flash(f"操作失败: {e}", "error")
    return redirect(url_for("scenes_list"))


# ============================================================
# Day10 新增: 告警记录管理
# ============================================================
@app.route("/alarms")
@login_required
def alarms_list():
    # 用独立变量保存过滤后的值, 不修改原始入参 (避免反模式)
    raw_status = request.args.get("status", "")
    raw_level = request.args.get("level", "")
    status = raw_status if raw_status in ("active", "acknowledged", "cleared") else ""
    level = raw_level if raw_level in VALID_LEVELS else ""
    alarms = list_alarms(status=status or None, level=level or None, limit=200)
    stats = get_alarm_stats()
    return render_template("alarms.html", alarms=alarms, stats=stats,
                           cur_status=status, cur_level=level,
                           level_labels=LEVEL_LABELS, level_colors=LEVEL_COLORS)


@app.route("/alarms/<int:aid>/ack", methods=["POST"])
@admin_required
def alarms_ack(aid):
    try:
        username = session.get("user", {}).get("username", "admin")
        acknowledge_alarm(aid, username)
        flash("告警已确认", "success")
    except Exception as e:
        flash(f"确认失败: {e}", "error")
    return redirect(url_for("alarms_list"))


@app.route("/alarms/<int:aid>/clear", methods=["POST"])
@admin_required
def alarms_clear(aid):
    try:
        clear_alarm(aid)
        flash("告警已清除", "success")
    except Exception as e:
        flash(f"清除失败: {e}", "error")
    return redirect(url_for("alarms_list"))


@app.route("/alarms/ack-all", methods=["POST"])
@admin_required
def alarms_ack_all():
    try:
        username = session.get("user", {}).get("username", "admin")
        acknowledge_all_alarms(username)
        flash("所有未确认告警已确认", "success")
    except Exception as e:
        flash(f"批量确认失败: {e}", "error")
    return redirect(url_for("alarms_list"))


@app.route("/alarms/clear-all", methods=["POST"])
@admin_required
def alarms_clear_all():
    try:
        clear_all_alarms()
        flash("所有告警已清除", "success")
    except Exception as e:
        flash(f"批量清除失败: {e}", "error")
    return redirect(url_for("alarms_list"))


@app.route("/alarms/test", methods=["POST"])
@admin_required
def alarms_test():
    """手动触发一条测试告警 (验证告警链路)"""
    level = request.form.get("level", "info")
    message = request.form.get("message", "手动测试告警").strip()
    # 前置校验: 非法 level 直接拒绝, 不进入 db 层
    if level not in VALID_LEVELS:
        flash(f"非法告警级别 '{level}', 只允许 {list(VALID_LEVELS)}", "error")
        return redirect(url_for("alarms_list"))
    if not message:
        flash("告警消息不能为空", "error")
        return redirect(url_for("alarms_list"))
    try:
        create_alarm(rule_id=None, rule_name="手动测试",
                     source_key="test", source_value="0",
                     level=level, message=message)
        flash(f"测试告警已产生 [{LEVEL_LABELS.get(level, level)}]", "success")
    except Exception as e:
        flash(f"测试告警失败: {e}", "error")
    return redirect(url_for("alarms_list"))


@app.route("/api/alarm-stats")
@login_required
def api_alarm_stats():
    """前端轮询获取告警统计 (看板实时刷新)"""
    return jsonify(get_alarm_stats())


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("WEB_PORT", "8081"))
    print(f"\nDay10 IoT 管理平台: http://127.0.0.1:{port}")
    print("默认账号: admin / admin123   user / user123")
    print("新增: /scenes 场景规则  /alarms 告警管理\n")
    app.run(host="0.0.0.0", port=port, debug=False)
