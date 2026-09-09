"""Day9 IoT 管理平台 - Flask Web 后端

提供:
  - 登录鉴权 (session-based, 区分 admin / user)
  - 看板 (统计设备映射数量)
  - 映射管理 CRUD (gateway_key → 虚拟产品/设备/属性)
  - 用户管理 CRUD (admin 专属)
  - 实物控制台 (继电器开关 + 传感器读数, 通过 MQTT 下发命令)
  - 在线用户 / 登录历史 (admin 专属)

运行:
  python web/app.py
  浏览器打开 http://127.0.0.1:8081
  默认账号: admin / admin123  或  user / user123
"""
import os
import sys
import json
import time
import threading
from functools import wraps

# 把 day9/ 目录加入 sys.path, 让 db.py 可被导入
_HERE = os.path.dirname(os.path.abspath(__file__))
_PARENT = os.path.dirname(_HERE)
if _PARENT not in sys.path:
    sys.path.insert(0, _PARENT)

from db import (
    init_db, load_all_mappings, add_mapping, update_mapping, delete_mapping,
    authenticate, list_users, add_user, update_user_role, delete_user, reset_password,
    start_session, end_session, touch_session, list_online_users,
    list_recent_sessions, get_online_count,
    get_device_status_all,
)

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify

app = Flask(__name__, static_folder=os.path.join(_HERE, "static"))
app.secret_key = "day9-iot-platform-secret-key-change-in-production"


# ============================================================
# MQTT 下发 (实物控制台用)
# ============================================================
_MQTT_LOCK = threading.Lock()
_MQTT_CLIENT = None

def _get_mqtt():
    """惰性创建 MQTT 客户端, 避免未安装 paho-mqtt 时启动失败"""
    global _MQTT_CLIENT
    if _MQTT_CLIENT is not None:
        return _MQTT_CLIENT
    try:
        from paho.mqtt import client as mqtt_client
    except ImportError:
        return None

    client = mqtt_client.Client(client_id="web-admin-day9", clean_session=True)
    client.username_pw_set("test", "123456")
    try:
        client.connect("172.16.4.211", 9783, keepalive=30)
        client.loop_start()
        _MQTT_CLIENT = client
        print("[Web] MQTT 客户端已连接 172.16.4.211:9783")
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


# ============================================================
# 上下文注入: 所有模板都能拿到当前用户
# ============================================================
@app.context_processor
def inject_user():
    return {"current_user": session.get("user")}


# ============================================================
# 会话心跳: 每次请求更新 last_seen (登录用户)
# ============================================================
@app.before_request
def _heartbeat_session():
    sess = session.get("user")
    if sess and "session_id" in sess:
        try:
            touch_session(sess["session_id"])
        except Exception:
            pass  # 心跳失败不影响正常请求


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
# 看板
# ============================================================
@app.route("/")
@app.route("/dashboard")
@login_required
def dashboard():
    mappings = load_all_mappings()
    enabled = [m for m in mappings if m["enabled"]]

    # 统计
    total_mappings = len(mappings)
    enabled_count = len(enabled)
    disabled_count = total_mappings - enabled_count

    # 按产品分组
    products = {}
    for m in enabled:
        p = m["product_id"]
        products.setdefault(p, 0)
        products[p] += 1

    # 网关侧 key 分类
    gateway_keys = {}
    for m in enabled:
        gk = m["gateway_key"]
        gateway_keys.setdefault(gk, m["description"] or gk)

    # 虚拟设备数 (去重)
    virtual_devices = set()
    for m in enabled:
        virtual_devices.add((m["product_id"], m["device_id"]))

    # 用户数
    user_count = len(list_users())

    # 在线用户数
    online_count = get_online_count()

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
    """快速切换启用/禁用"""
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
        add_user(
            username=request.form["username"].strip(),
            password=request.form["password"].strip(),
            role=request.form.get("role", "user"),
            display_name=request.form.get("display_name", "").strip(),
        )
        flash("用户创建成功", "success")
    except Exception as e:
        flash(f"创建失败: {e}", "error")
    return redirect(url_for("users_list"))


@app.route("/users/<int:uid>/role", methods=["POST"])
@admin_required
def users_role(uid):
    try:
        update_user_role(uid, request.form.get("role", "user"))
        flash("角色已更新", "success")
    except Exception as e:
        flash(f"更新失败: {e}", "error")
    return redirect(url_for("users_list"))


@app.route("/users/<int:uid>/password", methods=["POST"])
@admin_required
def users_password(uid):
    try:
        reset_password(uid, request.form.get("password", "").strip())
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
# API: 获取当前路由 (Bridge 热重载或前端轮询)
# ============================================================
@app.route("/api/routing")
@login_required
def api_routing():
    mappings = load_all_mappings()
    return jsonify({"count": len(mappings), "items": mappings})


# ============================================================
# 实物控制台 (admin 专属)
# ============================================================
# 网关设备 topic (与 Bridge 一致)
GATEWAY_PRODUCT = "relay-cc"
GATEWAY_DEVICE  = "relaycc"

# 继电器和传感器的展示分组
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
    # 读 config.json 获取采集点配置 (若存在)
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

    # 读 device_status 获取实时值
    status = get_device_status_all()
    # 合并映射描述
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
            "key": k,
            "desc": m.get("description", ""),
            "product": m.get("product_id", ""),
            "device": m.get("device_id", ""),
            "enabled": m.get("enabled", 0),
            "value": val_int,
            "updated_at": st.get("updated_at", ""),
        })

    sensor_cards = []
    for k in SENSOR_KEYS:
        m = mappings.get(k, {})
        st = status.get(k, {})
        sensor_cards.append({
            "key": k,
            "desc": m.get("description", ""),
            "product": m.get("product_id", ""),
            "value": st.get("value", "暂无数据"),
            "unit": SENSOR_UNITS.get(k, ""),
            "updated_at": st.get("updated_at", ""),
        })

    return render_template(
        "devices.html",
        relay_cards=relay_cards,
        sensor_cards=sensor_cards,
        modbus_points=modbus_points,
    )


@app.route("/devices/toggle", methods=["POST"])
@admin_required
def devices_toggle():
    """通过 MQTT 下发继电器开关命令到网关"""
    key = request.form.get("key", "").strip()
    value = request.form.get("value", "0").strip()

    # 校验 key
    if key not in RELAY_KEYS:
        return jsonify({"ok": False, "msg": f"无效的继电器 key: {key}"}), 400

    # 钳位 value
    try:
        val_int = 1 if int(value) == 1 else 0
    except (ValueError, TypeError):
        val_int = 0

    # 检查映射是否启用
    mappings = {m["gateway_key"]: m for m in load_all_mappings()}
    m = mappings.get(key)
    if not m:
        return jsonify({"ok": False, "msg": f"映射 {key} 不存在"}), 404
    if not m.get("enabled"):
        return jsonify({"ok": False, "msg": f"映射 {key} 已禁用, 无法控制"}), 403

    client = _get_mqtt()
    if not client:
        return jsonify({"ok": False, "msg": "MQTT 客户端未连接, 请检查网络或 paho-mqtt"}), 500

    topic = f"{GATEWAY_PRODUCT}/{GATEWAY_DEVICE}/properties/write"
    payload = {
        "timestamp": int(time.time() * 1000),
        "messageId": f"web-{int(time.time()*1000)}",
        "properties": {key: val_int},
    }
    try:
        info = client.publish(topic, json.dumps(payload), qos=1)
        print(f"[Web] 下发命令: {topic} -> {payload} (mid={info.mid})")
        return jsonify({"ok": True, "msg": f"已下发 {key}={'开' if val_int else '关'}"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"下发失败: {e}"}), 500


@app.route("/devices/all", methods=["POST"])
@admin_required
def devices_all():
    """一键全开 / 全关"""
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
        label = "全开" if target_val else "全关"
        print(f"[Web] 一键{label}: {props}")
        return jsonify({"ok": True, "msg": f"已下发{label}命令: {props}"})
    except Exception as e:
        return jsonify({"ok": False, "msg": f"下发失败: {e}"}), 500


@app.route("/api/device-status")
@login_required
def api_device_status():
    """前端轮询获取最新设备状态"""
    status = get_device_status_all()
    return jsonify(status)


# ============================================================
# 在线用户 / 登录历史 (admin 专属)
# ============================================================
@app.route("/sessions")
@admin_required
def sessions_list():
    online = list_online_users()
    history = list_recent_sessions(limit=30)
    return render_template("sessions.html", online=online, history=history)


# ============================================================
# 采集点配置 (只读展示)
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
    return render_template("config_points.html", config=config_data)


# ============================================================
# 入口
# ============================================================
if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("WEB_PORT", "8081"))
    print(f"\nDay9 IoT 管理平台: http://127.0.0.1:{port}")
    print("默认账号: admin / admin123   user / user123\n")
    app.run(host="0.0.0.0", port=port, debug=False)
