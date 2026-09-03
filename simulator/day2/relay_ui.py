"""继电器 Web UI 控制台 - 双通道控制

两种控制模式 (网页顶部随时切换):
  1. MQTT 链路模式 (默认): 扮演"迷你 JetLinks 平台"
     - 单路开关: 发布 /{productId}/{deviceId}/properties/write 给 relay_simulator_jl.py
     - 全开/全关: 发布 /{productId}/{deviceId}/function/invoke (all_on / all_off)
     - 状态: 订阅 properties/report, 模拟器执行后上报, UI 实时刷新
     - 附带实时消息日志窗口, 完整展示 命令下发 -> 设备执行 -> 状态回传 链路
  2. 直连 Modbus 模式: UI 直接读写从站寄存器, 不依赖模拟器和 EMQX

运行: python relay_ui.py   然后浏览器打开 http://127.0.0.1:8080
依赖: pip install pymodbus==3.6.9 paho-mqtt==1.6.1 flask==3.0.3
配置: 复用 config_relay.json (modbus / mqtt / jetlinks / register_map / relay_order)
"""

import json
import random
import threading
import time
import uuid
from collections import deque
from datetime import datetime

from flask import Flask, jsonify, request
import paho.mqtt.client as mqtt
from pymodbus.client import ModbusTcpClient

CONFIG_PATH = "config_relay.json"
UI_PORT = 8081
RECONNECT_S = 5
RETRY_MODBUS_S = 3          # 直连模式读失败后的重连限频

app = Flask(__name__)

# ---------- 全局状态 ----------
cfg = {}
mb_cfg = {}
mq_cfg = {}
jl_cfg = {}
reg_map = {}                 # "0" -> {name: relay1, ...} (相对 register_start 的偏移)
relay_names = []             # ["relay1" ... "relay8"]

state_lock = threading.Lock()
mode = "mqtt"                # 当前活动通道: "mqtt" / "modbus"
mqtt_relays = {}             # MQTT 模式状态 (来自 properties/report 订阅)
modbus_relays = {}           # 直连模式状态 (来自寄存器轮询)
mqtt_connected = False
modbus_connected = False
logs = deque(maxlen=100)     # 消息日志环形队列

mb_client = None
mb_last_retry = 0.0
mb_lock = threading.Lock()   # Modbus 读写互斥

mqtt_client = None
TOPIC_REPORT = ""
TOPIC_WRITE = ""
TOPIC_INVOKE = ""


# ==================== 工具函数 ====================

def load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def now_ms():
    return int(time.time() * 1000)


def gen_message_id():
    return "ui-" + str(uuid.uuid4())[:8]


def add_log(direction, topic_tag, text):
    """direction: 'up'=UI 发出, 'down'=设备上报, 'info'=系统提示"""
    logs.append({
        "t": datetime.now().strftime("%H:%M:%S"),
        "dir": direction,
        "topic": topic_tag,
        "text": text,
    })


def clamp01(val):
    """继电器开关量钳位: 防止从站脏值"""
    try:
        return 1 if int(val) else 0
    except (ValueError, TypeError):
        return 0


def to_signed(raw):
    return raw - 65536 if raw > 32767 else raw


# ==================== MQTT 通道 ====================

def mqtt_on_connect(client, _userdata, _flags, rc):
    global mqtt_connected
    if rc != 0:
        add_log("info", "system", f"MQTT 连接失败 rc={rc}")
        return
    mqtt_connected = True
    client.subscribe(TOPIC_REPORT, qos=1)
    add_log("info", "system", f"MQTT 已连接 EMQX, 订阅 {TOPIC_REPORT}")


def mqtt_on_disconnect(_client, _userdata, rc):
    global mqtt_connected
    mqtt_connected = False
    add_log("info", "system", f"MQTT 断开 rc={rc}, 自动重连中")


def mqtt_on_message(_client, _userdata, msg):
    """收到模拟器上报的 properties/report -> 更新状态缓存 + 记日志"""
    text = msg.payload.decode("utf-8", "replace")
    try:
        payload = json.loads(text)
    except ValueError:
        return
    props = payload.get("properties", {})
    relays = {k: clamp01(v) for k, v in props.items() if k.startswith("relay")}
    if not relays:
        return
    with state_lock:
        mqtt_relays.update(relays)
    brief = " ".join(f"{k}={'开' if v else '关'}" for k, v in relays.items())
    add_log("down", "report", brief)


def mqtt_start():
    global mqtt_client
    client_id = f"relayui-jl-{random.randint(1000, 9999)}"   # 唯一 client_id, 避免互踢
    mqtt_client = mqtt.Client(client_id=client_id, clean_session=True)
    if mq_cfg.get("username"):
        mqtt_client.username_pw_set(mq_cfg["username"], mq_cfg.get("password"))
    mqtt_client.on_connect = mqtt_on_connect
    mqtt_client.on_disconnect = mqtt_on_disconnect
    mqtt_client.on_message = mqtt_on_message
    mqtt_client.reconnect_delay_set(min_delay=5, max_delay=60)
    mqtt_client.connect_async(mq_cfg.get("host", "127.0.0.1"),
                              int(mq_cfg.get("port", 1883)), keepalive=60)
    mqtt_client.loop_start()
    add_log("info", "system", f"MQTT 连接中 {mq_cfg.get('host')}:{mq_cfg.get('port')} (client_id={client_id})")


def mqtt_publish(topic, payload, tag):
    """发布命令, retain=False 防止 EMQX 存脏数据"""
    if mqtt_client is None or not mqtt_connected:
        add_log("info", "system", "MQTT 未连接, 无法发送命令")
        return False
    text = json.dumps(payload, ensure_ascii=False)
    try:
        info = mqtt_client.publish(topic, text, qos=1, retain=False)
        ok = info.rc == mqtt.MQTT_ERR_SUCCESS
        if ok:
            brief = json.dumps(payload.get("properties") or
                               {"functionId": payload.get("functionId")},
                               ensure_ascii=False)
            add_log("up", tag, brief)
        else:
            add_log("info", "system", f"发布失败 rc={info.rc}")
        return ok
    except (OSError, RuntimeError) as e:
        add_log("info", "system", f"MQTT 发布异常: {e}")
        return False


def mqtt_control_single(name, value):
    """单路控制: 走 JetLinks 属性写入格式"""
    payload = {"messageId": gen_message_id(), "properties": {name: clamp01(value)}}
    return mqtt_publish(TOPIC_WRITE, payload, "write")


def mqtt_control_all(value):
    """全开/全关: 走 JetLinks 功能调用 all_on / all_off"""
    func = "all_on" if value else "all_off"
    payload = {"messageId": gen_message_id(), "functionId": func, "inputs": []}
    return mqtt_publish(TOPIC_INVOKE, payload, "invoke")


# ==================== Modbus 直连通道 ====================

def modbus_connect():
    global mb_client, modbus_connected
    client = ModbusTcpClient(mb_cfg["host"], port=int(mb_cfg["port"]))
    if client.connect():
        mb_client = client
        modbus_connected = True
        add_log("info", "system", f"Modbus 已连接 {mb_cfg['host']}:{mb_cfg['port']} unit={mb_cfg.get('unit_id')}")
    else:
        modbus_connected = False
    return modbus_connected


def modbus_close():
    global mb_client, modbus_connected
    if mb_client:
        try:
            mb_client.close()
        except Exception:
            pass
        mb_client = None
    modbus_connected = False


def modbus_read_relays():
    """读全部继电器寄存器 -> {relay1: 0/1, ...} 失败返回 None"""
    global mb_client, mb_last_retry, modbus_connected
    with mb_lock:
        if mb_client is None:
            now = time.time()
            if now - mb_last_retry >= RETRY_MODBUS_S:
                mb_last_retry = now
                modbus_connect()
            if mb_client is None:
                return None
        try:
            rr = mb_client.read_holding_registers(int(mb_cfg.get("register_start", 2)),
                                                  count=int(mb_cfg.get("register_count", 8)),
                                                  slave=int(mb_cfg.get("unit_id", 1)))
            if rr.isError():
                modbus_close()
                return None
            values = {}
            for idx, spec in reg_map.items():
                i = int(idx)
                if i >= len(rr.registers):
                    continue
                values[spec["name"]] = clamp01(rr.registers[i])
            return values
        except Exception:
            modbus_close()
            return None


def modbus_write_relay(name, value):
    """写单个继电器寄存器, 返回是否成功"""
    global mb_client, mb_last_retry
    with mb_lock:
        if mb_client is None:
            now = time.time()
            if now - mb_last_retry >= RETRY_MODBUS_S:
                mb_last_retry = now
                modbus_connect()
            if mb_client is None:
                return False
        reg_addr = None
        for offset, spec in reg_map.items():
            if spec["name"] == name:
                reg_addr = int(mb_cfg.get("register_start", 2)) + int(offset)
                break
        if reg_addr is None:
            return False
        try:
            rr = mb_client.write_register(reg_addr, clamp01(value),
                                          slave=int(mb_cfg.get("unit_id", 1)))
            if rr.isError():
                return False
            add_log("up", "modbus", f"{name}={'开' if value else '关'} -> reg{reg_addr}")
            return True
        except Exception as e:
            add_log("info", "system", f"Modbus 写入异常: {e}")
            modbus_close()
            return False


# ==================== Flask API ====================

def current_status():
    with state_lock:
        relays = dict(mqtt_relays if mode == "mqtt" else modbus_relays)
    connected = mqtt_connected if mode == "mqtt" else modbus_connected
    # 补齐 8 路默认值 0, 避免前端缺卡片
    for name in relay_names:
        relays.setdefault(name, 0)
    return {
        "mode": mode,
        "connected": connected,
        "relays": {name: relays[name] for name in relay_names},
        "log_visible": mode == "mqtt",
        "logs": list(logs)[-50:],
    }


@app.get("/")
def index():
    return PAGE_HTML


@app.get("/api/status")
def api_status():
    global modbus_relays
    if mode == "modbus":
        values = modbus_read_relays()
        if values is not None:
            with state_lock:
                modbus_relays = values
    return jsonify(current_status())


@app.post("/api/control")
def api_control():
    body = request.get_json(silent=True) or {}
    action = body.get("action")
    value = 1 if body.get("value") in (1, "1", True, "on", "open") else 0

    if action == "single":
        name = str(body.get("name", ""))
        if name not in relay_names:
            return jsonify({"success": False, "error": f"未知继电器 {name}"}), 400
        if mode == "mqtt":
            ok = mqtt_control_single(name, value)
        else:
            ok = modbus_write_relay(name, value)
            if ok:
                with state_lock:
                    modbus_relays[name] = clamp01(value)
        return jsonify({"success": ok})

    if action == "all":
        if mode == "mqtt":
            ok = mqtt_control_all(value)
        else:
            ok = all(modbus_write_relay(name, value) for name in relay_names)
            if ok:
                with state_lock:
                    for name in relay_names:
                        modbus_relays[name] = clamp01(value)
        return jsonify({"success": ok})

    return jsonify({"success": False, "error": "无效 action"}), 400


@app.post("/api/mode")
def api_mode():
    global mode
    new_mode = request.get_json(silent=True, force=True).get("mode") \
        if request.get_data() else None
    if new_mode not in ("mqtt", "modbus"):
        return jsonify({"success": False, "error": "无效 mode"}), 400
    if new_mode != mode:
        mode = new_mode
        if mode == "modbus":
            add_log("info", "system", "切换到直连 Modbus 模式 (平台报文不产生, 日志暂停)")
            values = modbus_read_relays()
            if values is not None:
                with state_lock:
                    modbus_relays.update(values)
        else:
            modbus_close()
            add_log("info", "system", "切换到 MQTT 链路模式")
    return jsonify({"success": True, "mode": mode})


# ==================== 前端页面 (内嵌) ====================

PAGE_HTML = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>继电器控制中心</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
    background: #0f172a; color: #e2e8f0; min-height: 100vh;
    display: flex; flex-direction: column; align-items: center; padding: 24px 16px;
  }
  header { width: 100%; max-width: 860px; display: flex; align-items: center;
           justify-content: space-between; flex-wrap: wrap; gap: 12px; margin-bottom: 24px; }
  h1 { font-size: 22px; letter-spacing: 1px; }
  .right { display: flex; align-items: center; gap: 16px; }
  .tabs { display: flex; background: #1e293b; border-radius: 10px; padding: 4px; }
  .tabs button {
    border: none; background: transparent; color: #94a3b8; padding: 8px 16px;
    border-radius: 8px; cursor: pointer; font-size: 14px; transition: all .2s;
  }
  .tabs button.active { background: #3b82f6; color: #fff; }
  .badge { display: flex; align-items: center; gap: 8px; font-size: 13px; color: #94a3b8; }
  .dot { width: 10px; height: 10px; border-radius: 50%; background: #64748b; }
  .dot.on { background: #22c55e; box-shadow: 0 0 8px #22c55e; }
  .dot.busy { background: #eab308; }

  #grid { width: 100%; max-width: 860px; display: grid;
          grid-template-columns: repeat(4, 1fr); gap: 14px; }
  @media (max-width: 640px) { #grid { grid-template-columns: repeat(2, 1fr); } }
  .card {
    background: #1e293b; border: 1px solid #334155; border-radius: 14px;
    padding: 18px 14px; display: flex; flex-direction: column; align-items: center;
    gap: 14px; transition: border-color .2s; cursor: pointer;
  }
  .card:hover { border-color: #3b82f6; }
  .card .name { font-size: 15px; font-weight: 600; }
  .card .tag { font-size: 11px; color: #64748b; }
  .switch { width: 52px; height: 28px; border-radius: 14px; background: #475569;
            position: relative; transition: background .25s; }
  .switch::after {
    content: ""; position: absolute; top: 3px; left: 3px; width: 22px; height: 22px;
    border-radius: 50%; background: #cbd5e1; transition: all .25s;
  }
  .card.on .switch { background: #22c55e; }
  .card.on .switch::after { left: 27px; background: #fff; }
  .card.on { border-color: #22c55e55; }
  .card.on .name { color: #4ade80; }

  .actions { width: 100%; max-width: 860px; display: flex; gap: 14px; margin: 20px 0; }
  .actions button {
    flex: 1; padding: 13px 0; border: none; border-radius: 10px; font-size: 15px;
    font-weight: 600; cursor: pointer; transition: opacity .2s;
  }
  .actions button:hover { opacity: .85; }
  #btn-all-on { background: #16a34a; color: #fff; }
  #btn-all-off { background: #475569; color: #e2e8f0; }

  #log-box { width: 100%; max-width: 860px; background: #0b1120;
             border: 1px solid #334155; border-radius: 12px; overflow: hidden; }
  #log-box.hidden { display: none; }
  .log-head { padding: 10px 16px; background: #1e293b; font-size: 13px;
              color: #94a3b8; display: flex; justify-content: space-between; }
  #log-body { height: 220px; overflow-y: auto; padding: 10px 16px;
              font-family: Consolas, monospace; font-size: 12.5px; line-height: 1.8; }
  .log-line .t { color: #64748b; margin-right: 10px; }
  .log-line .arrow-up { color: #f59e0b; margin-right: 6px; }
  .log-line .arrow-down { color: #38bdf8; margin-right: 6px; }
  .log-line .arrow-info { color: #64748b; margin-right: 6px; }
  .log-line .tp { color: #a78bfa; margin-right: 8px; }
  #empty-tip { width: 100%; max-width: 860px; text-align: center; color: #64748b;
               font-size: 13px; padding: 16px 0; }
</style>
</head>
<body>
<header>
  <h1>继电器控制中心</h1>
  <div class="right">
    <div class="tabs">
      <button id="tab-mqtt" class="active" onclick="switchMode('mqtt')">MQTT 链路</button>
      <button id="tab-modbus" onclick="switchMode('modbus')">直连 Modbus</button>
    </div>
    <div class="badge"><span class="dot" id="dot"></span><span id="badge-text">连接中</span></div>
  </div>
</header>

<div id="grid"></div>

<div class="actions">
  <button id="btn-all-on" onclick="controlAll(1)">全部打开</button>
  <button id="btn-all-off" onclick="controlAll(0)">全部关闭</button>
</div>

<div id="log-box">
  <div class="log-head"><span>消息日志</span><span>↑ 命令下发 &nbsp; ↓ 状态上报</span></div>
  <div id="log-body"></div>
</div>
<div id="empty-tip" style="display:none">直连模式不产生平台报文, 日志暂停</div>

<script>
let relays = {};
let curMode = "mqtt";
let connected = false;

function renderGrid() {
  const grid = document.getElementById("grid");
  grid.innerHTML = "";
  for (let i = 1; i <= 8; i++) {
    const name = "relay" + i;
    const on = relays[name] === 1;
    const card = document.createElement("div");
    card.className = "card" + (on ? " on" : "");
    card.innerHTML =
      '<div class="name">' + name + '</div>' +
      '<div class="tag">寄存器 reg' + (i + 1) + '</div>' +
      '<div class="switch"></div>';
    card.onclick = () => controlSingle(name);
    grid.appendChild(card);
  }
}

async function fetchStatus() {
  try {
    const r = await fetch("/api/status");
    const s = await r.json();
    curMode = s.mode;
    connected = s.connected;
    relays = s.relays;
    renderGrid();
    updateBadge();
    updateModeTabs();
    updateLog(s);
  } catch (e) { /* 服务未就绪, 忽略 */ }
}

function updateBadge() {
  const dot = document.getElementById("dot");
  const text = document.getElementById("badge-text");
  if (connected) {
    dot.className = "dot on";
    text.textContent = curMode === "mqtt" ? "EMQX 已连接" : "从站已连接";
  } else {
    dot.className = "dot";
    text.textContent = curMode === "mqtt" ? "EMQX 未连接" : "从站未连接";
  }
}

function updateModeTabs() {
  document.getElementById("tab-mqtt").className = curMode === "mqtt" ? "active" : "";
  document.getElementById("tab-modbus").className = curMode === "modbus" ? "active" : "";
}

function updateLog(s) {
  const box = document.getElementById("log-box");
  const tip = document.getElementById("empty-tip");
  if (!s.log_visible) { box.classList.add("hidden"); tip.style.display = "block"; return; }
  box.classList.remove("hidden"); tip.style.display = "none";
  const body = document.getElementById("log-body");
  body.innerHTML = s.logs.map(l => {
    const arrow = l.dir === "up" ? '<span class="arrow-up">↑</span>'
                : l.dir === "down" ? '<span class="arrow-down">↓</span>'
                : '<span class="arrow-info">·</span>';
    const tp = l.topic && l.topic !== "system" ? '<span class="tp">[' + l.topic + ']</span>' : '';
    return '<div class="log-line"><span class="t">' + l.t + '</span>' + arrow + tp + l.text + '</div>';
  }).join("");
  body.scrollTop = body.scrollHeight;
}

async function controlSingle(name) {
  const target = relays[name] === 1 ? 0 : 1;
  relays[name] = target;   // 乐观更新, 失败时由 2 秒轮询自动纠正
  renderGrid();
  try {
    await fetch("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "single", name: name, value: target })
    });
  } catch (e) {}
  setTimeout(fetchStatus, 400);
}

async function controlAll(value) {
  for (const k of Object.keys(relays)) relays[k] = value;
  renderGrid();
  try {
    await fetch("/api/control", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ action: "all", value: value })
    });
  } catch (e) {}
  setTimeout(fetchStatus, 400);
}

async function switchMode(m) {
  if (m === curMode) return;
  const dot = document.getElementById("dot");
  dot.className = "dot busy";
  document.getElementById("badge-text").textContent = "切换中...";
  try {
    await fetch("/api/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: m })
    });
  } catch (e) {}
  fetchStatus();
}

fetchStatus();
setInterval(fetchStatus, 2000);
</script>
</body>
</html>"""


# ==================== 启动 ====================

def main():
    global cfg, mb_cfg, mq_cfg, jl_cfg, reg_map, relay_names
    global TOPIC_REPORT, TOPIC_WRITE, TOPIC_INVOKE

    cfg = load_json(CONFIG_PATH, {})
    mb_cfg = cfg.get("modbus", {})
    mq_cfg = cfg.get("mqtt", {})
    jl_cfg = cfg.get("jetlinks", {})
    reg_map = cfg.get("register_map", {})

    # 继电器名称按寄存器偏移排序, 保证 relay1~relay8 顺序
    relay_names = [spec["name"] for _, spec in
                   sorted(reg_map.items(), key=lambda kv: int(kv[0]))
                   if spec["name"].startswith("relay")]

    product_id = jl_cfg.get("product_id", "")
    device_id = jl_cfg.get("device_id", "")
    TOPIC_REPORT = f"/{product_id}/{device_id}/properties/report"
    TOPIC_WRITE = f"/{product_id}/{device_id}/properties/write"
    TOPIC_INVOKE = f"/{product_id}/{device_id}/function/invoke"

    add_log("info", "system", f"继电器控制台启动, 浏览器打开 http://127.0.0.1:{UI_PORT}")
    add_log("info", "system", f"继电器: {', '.join(relay_names)}")
    mqtt_start()   # MQTT 常驻连接 (无论当前模式), 保证 report 状态随时可用

    app.run(host="0.0.0.0", port=UI_PORT, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
