"""Day10.2 大屏后端 — Flask REST + WebSocket + 后台数据轮询广播.

架构:
  数据源 (bridge 子进程 / fake_bridge)
      │ 写 SQLite (device_status / alarm_records / scene_rules)
      ▼
  本进程后台轮询线程 (0.5s 扫一次)
      │ 检测变化 → record_history + hub.broadcast
      ▼
  WebSocket /ws/dashboard → 大屏 Vue

运行:
  pip install flask flask-sock paho-mqtt
  python app.py          # 端口 8083
"""
import os
import sys
import time
import mimetypes
import threading

# Windows 下 .js 可能被识别为 text/plain, 导致浏览器拒绝执行 ES module
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")

from flask import Flask, send_from_directory
from flask_sock import Sock

import db
from api import bp as api_bp
from ws_hub import (
    hub, EV_DEVICE_STATUS, EV_ALARM_NEW, EV_RULE_TRIGGERED,
    EV_HISTORY_TICK, EV_OVERVIEW_TICK,
)
from bridge_runner import choose_and_start

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
FRONTEND_DIST = os.path.join(_PROJECT_ROOT, "frontend", "dist")

app = Flask(__name__, static_folder=FRONTEND_DIST, static_url_path="/")
app.register_blueprint(api_bp, url_prefix="/api")
sock = Sock(app)


# ============================================================
# WebSocket 端点
# ============================================================
@sock.route("/ws/dashboard")
def ws_dashboard(ws):
    hub.register(ws)
    try:
        # 连接后立即推一份全量快照, 让大屏首屏有数据
        try:
            flat = {k: v["value"] for k, v in db.get_device_status_all().items()}
            ws.send(_msg(EV_DEVICE_STATUS, flat))
        except Exception:
            pass
        while True:
            ws.receive(timeout=30)  # 仅维持连接; 超时则发心跳保活
    except Exception:
        pass
    finally:
        hub.unregister(ws)


def _msg(ev_type, data):
    import json
    return json.dumps({"type": ev_type, "data": data, "ts": time.time()},
                      ensure_ascii=False, default=str)


# ============================================================
# 前端静态资源 (Vite build 后由 Flask 托管; dev 模式用 Vite 5173)
# ============================================================
@app.route("/")
def index():
    if os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
        return send_from_directory(FRONTEND_DIST, "index.html")
    return ("<h2>前端尚未构建</h2><p>请先执行 <code>cd frontend &amp;&amp; npm install &amp;&amp; npm run build</code>，"
            "或开发模式访问 <a href='http://localhost:5173'>http://localhost:5173</a></p>")


@app.route("/<path:path>")
def spa(path):
    if path.startswith("api/"):
        return ("Not Found", 404)
    full = os.path.join(FRONTEND_DIST, path)
    if os.path.isfile(full):
        return send_from_directory(FRONTEND_DIST, path)
    # SPA fallback
    if os.path.exists(os.path.join(FRONTEND_DIST, "index.html")):
        return send_from_directory(FRONTEND_DIST, "index.html")
    return ("Not Found", 404)


# ============================================================
# 后台轮询线程: 检测 SQLite 变化 → 写历史 → 广播 WS
# ============================================================
class DataWatcher:
    def __init__(self, source: str):
        self.source = source              # 'bridge' | 'simulator'
        self.last_status = {}             # {key: value}
        self.last_max_alarm_id = 0
        self.last_rule_counts = {}       # {rule_id: trigger_count}
        self._stop = threading.Event()

    def run(self):
        # 初始化基线
        self._init_baseline()
        last_tick = 0
        last_cleanup = 0
        print("[watcher] 数据轮询线程已启动")
        while not self._stop.is_set():
            try:
                self._poll_status()
                self._poll_alarms()
                self._poll_rules()
                now = time.time()
                # 每 5 秒推历史 + 概览
                if now - last_tick >= 5:
                    self._push_ticks()
                    last_tick = now
                # 每 30 秒清理过期历史
                if now - last_cleanup >= 30:
                    deleted = db.cleanup_old_history()
                    if deleted:
                        print(f"[watcher] 清理过期历史 {deleted} 条")
                    last_cleanup = now
            except Exception as e:
                print(f"[watcher] 轮询异常: {e}")
            self._stop.wait(0.5)

    def _init_baseline(self):
        for k, v in db.get_device_status_all().items():
            self.last_status[k] = v["value"]
        alarms = db.get_recent_alarms(1)
        self.last_max_alarm_id = alarms[0]["id"] if alarms else 0
        for r in db.list_scene_rules():
            self.last_rule_counts[r["id"]] = r["trigger_count"]

    def _poll_status(self):
        current = db.get_device_status_all()
        flat = {k: v["value"] for k, v in current.items()}
        changed = False
        for k, v in flat.items():
            if self.last_status.get(k) != v:
                # 状态变化 → 写历史
                db.record_history(k, v, source=self.source)
                self.last_status[k] = v
                changed = True
        # 删除已不存在的 key
        for k in list(self.last_status.keys()):
            if k not in flat:
                del self.last_status[k]
                changed = True
        if changed:
            hub.broadcast(EV_DEVICE_STATUS, flat)

    def _poll_alarms(self):
        recent = db.get_recent_alarms(20)
        new_ones = [a for a in recent if a["id"] > self.last_max_alarm_id]
        if new_ones:
            # 按 id 升序逐条广播
            for a in sorted(new_ones, key=lambda x: x["id"]):
                hub.broadcast(EV_ALARM_NEW, a)
            self.last_max_alarm_id = max(a["id"] for a in new_ones)

    def _poll_rules(self):
        for r in db.list_scene_rules():
            prev = self.last_rule_counts.get(r["id"], 0)
            if r["trigger_count"] > prev:
                hub.broadcast(EV_RULE_TRIGGERED, {
                    "id": r["id"],
                    "name": r["name"],
                    "action_type": r["action_type"],
                    "trigger_count": r["trigger_count"],
                })
                self.last_rule_counts[r["id"]] = r["trigger_count"]

    def _push_ticks(self):
        # 历史折线
        hub.broadcast(EV_HISTORY_TICK, db.get_latest_history_tick(minutes=30))
        # 概览统计
        hub.broadcast(EV_OVERVIEW_TICK, db.get_overview())

    def stop(self):
        self._stop.set()


# ============================================================
# 入口
# ============================================================
def main():
    db.init_db()
    port = int(os.environ.get("DAY102_PORT", "8083"))

    # 1. 启动数据源子进程 (真实 bridge 或 fake_bridge)
    runner, source, _ = choose_and_start()

    # 2. 启动后台轮询广播线程
    watcher = DataWatcher(source=source)
    wt = threading.Thread(target=watcher.run, daemon=True)
    wt.start()

    print("=" * 56)
    print(f"  Day10.2 大屏后端已启动")
    print(f"  REST API:  http://localhost:{port}/api/overview")
    print(f"  WebSocket: ws://localhost:{port}/ws/dashboard")
    print(f"  数据源:    {source}")
    print(f"  大屏(dev): http://localhost:5173  (npm run dev)")
    print("=" * 56)

    try:
        # threaded=True 支持多 WS 连接并发
        app.run(host="0.0.0.0", port=port, debug=False, threaded=True,
                use_reloader=False)
    finally:
        watcher.stop()
        runner.stop()


if __name__ == "__main__":
    main()
