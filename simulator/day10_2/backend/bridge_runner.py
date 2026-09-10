"""Bridge Runner — 启动并监控数据源子进程, 崩溃自动重启.

数据源二选一 (app.py 启动时根据 MQTT 可达性决定):
  - MQTT 可达 → bridge/gateway_bridge.py  (真实 ESP32 → EMQX 数据)
  - MQTT 不可达 → simulator/fake_bridge.py (模拟数据, 保证大屏可演示)
"""
import os
import sys
import time
import socket
import subprocess
import threading

import db

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_HERE)
LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")
os.makedirs(LOG_DIR, exist_ok=True)


def mqtt_reachable(timeout: float = 2.0) -> bool:
    """TCP 探测 MQTT broker 是否可达."""
    try:
        cfg = db.load_gateway_config()
        host, port = cfg["mqtt_host"], cfg["mqtt_port"]
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except Exception:
        return False


class BridgeRunner:
    """以子进程方式运行数据源脚本, 监控存活, 崩溃 5 秒后重启."""

    def __init__(self, script_path: str, log_name: str = "bridge.log"):
        self.script_path = script_path
        self.log_path = os.path.join(LOG_DIR, log_name)
        self.proc = None
        self.should_run = True
        self._log_fp = None

    def start(self):
        self._log_fp = open(self.log_path, "a", encoding="utf-8", buffering=1)
        self._log_fp.write(f"\n===== {time.strftime('%Y-%m-%d %H:%M:%S')} 启动 =====\n")
        self.proc = subprocess.Popen(
            [sys.executable, "-u", self.script_path, "--hot-reload"],
            stdout=self._log_fp,
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(self.script_path),
        )
        print(f"[runner] 数据源已启动 pid={self.proc.pid} → {os.path.basename(self.script_path)}")
        print(f"[runner] 日志: {self.log_path}")

    def watch(self):
        """监控循环 (放独立线程跑)."""
        while self.should_run:
            if self.proc is None or self.proc.poll() is not None:
                if self.should_run:
                    print("[runner] 数据源进程退出, 5 秒后重启...")
                    time.sleep(5)
                    try:
                        self.start()
                    except Exception as e:
                        print(f"[runner] 重启失败: {e}")
                        time.sleep(5)
            time.sleep(3)

    def stop(self):
        self.should_run = False
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except Exception:
                self.proc.kill()
        if self._log_fp:
            self._log_fp.close()


def choose_and_start():
    """选择数据源并启动, 返回 (runner, source_label, watch_thread).

    优先级:
      1. 环境变量 DAY102_FORCE_FAKE=1 → 强制模拟模式 (现场无 ESP32 演示)
      2. MQTT 可达 → 真实 Bridge (ESP32 -> EMQX)
      3. MQTT 不可达 → FakeBridge 模拟数据 (保证大屏不空白)
    """
    real_bridge = os.path.join(_PROJECT_ROOT, "bridge", "gateway_bridge.py")
    fake_bridge = os.path.join(_PROJECT_ROOT, "simulator", "fake_bridge.py")

    force_fake = os.environ.get("DAY102_FORCE_FAKE", "") == "1"

    if force_fake:
        print("[runner] DAY102_FORCE_FAKE=1 → 强制 FakeBridge 模拟模式")
        runner = BridgeRunner(fake_bridge, log_name="fake_bridge.log")
        source = "simulator"
    elif mqtt_reachable():
        print("[runner] MQTT broker 可达 → 启动真实 Bridge")
        runner = BridgeRunner(real_bridge, log_name="bridge.log")
        source = "bridge"
    else:
        print("[runner] MQTT broker 不可达 → 回退到 FakeBridge (模拟数据)")
        runner = BridgeRunner(fake_bridge, log_name="fake_bridge.log")
        source = "simulator"

    runner.start()
    t = threading.Thread(target=runner.watch, daemon=True)
    t.start()
    return runner, source, t
