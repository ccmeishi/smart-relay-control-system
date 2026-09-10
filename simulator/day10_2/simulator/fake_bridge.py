"""Day10.2 Fake Bridge — MQTT/真实设备不可达时的模拟数据源.

用途:
  - 当 172.16.4.211:9783 (EMQX) 内网不可达, 或没有 ESP32 实物时,
    用本脚本直接向 SQLite 写模拟上报数据, 让大屏完整演示全链路.
  - 模拟温度/湿度/人体/烟雾随机漂移, 并评估场景规则 → 产生告警,
    继电器动作直接写回 device_status (模拟设备执行结果).

数据流向:
  fake_bridge → SQLite(device_status/alarm_records)
              → Flask 后台轮询 → WebSocket → 大屏

运行:
  python fake_bridge.py          # 持续模拟
  python fake_bridge.py --once   # 写一批就退出 (调试用)
"""
import os
import sys
import time
import random

# 导入 backend/db.py
_HERE = os.path.dirname(os.path.abspath(__file__))
_BACKEND_DIR = os.path.join(os.path.dirname(_HERE), "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import db

RELAY_KEYS = ["relay1", "relay2", "relay3", "relay4"]


class FakeBridge:
    """模拟网关: 维护一组缓慢漂移的传感器值 + 继电器状态."""

    def __init__(self):
        self.temperature = 26.0
        self.humidity = 55.0
        self.human = 1
        self.smoke = 8
        self.relays = {k: "0" for k in RELAY_KEYS}
        self.relays["relay2"] = "1"  # 默认灯开
        self.tick = 0

    def _drift(self, val, lo, hi, step):
        """随机游走 + 边界回弹."""
        val += random.uniform(-step, step)
        if val < lo:
            val = lo + random.uniform(0, step)
        if val > hi:
            val = hi - random.uniform(0, step)
        return round(val, 1)

    def step_once(self):
        """推进一个模拟周期: 更新传感器 → 写库 → 评估规则 → 模拟动作."""
        self.tick += 1

        # 1. 传感器漂移
        self.temperature = self._drift(self.temperature, 24.0, 31.0, 0.4)
        self.humidity = self._drift(self.humidity, 45.0, 68.0, 0.8)
        self.smoke = self._drift(self.smoke, 3.0, 20.0, 1.2)
        # 人体感应: 大部分时间保持, 每 ~20 个周期有机会翻转
        if random.random() < 0.06:
            self.human = 1 - self.human

        # 2. 写 device_status (模拟网关上报)
        db.update_device_status("temperature", str(self.temperature))
        db.update_device_status("humidity", str(self.humidity))
        db.update_device_status("human", str(self.human))
        db.update_device_status("smoke", str(int(self.smoke)))
        for k in RELAY_KEYS:
            db.update_device_status(k, self.relays[k])

        # 3. 评估场景规则 (对每个传感器 key), 模拟 bridge 的规则引擎
        for key, val in (("temperature", self.temperature),
                         ("humidity", self.humidity),
                         ("human", self.human),
                         ("smoke", self.smoke)):
            actions = db.evaluate_scene_rules(key, val)
            for act in actions:
                self._apply_action(act)

    def _apply_action(self, act):
        """模拟设备执行场景动作 (无真实 MQTT, 直接改继电器状态 + 写告警)."""
        atype = act.get("action_type")
        target = act.get("action_target", "")
        value = act.get("action_value", "0")
        try:
            val_int = 1 if int(float(value)) == 1 else 0
        except (ValueError, TypeError):
            val_int = 0

        changed = False
        if atype == "set_relay" and target in self.relays:
            if self.relays[target] != str(val_int):
                self.relays[target] = str(val_int)
                db.update_device_status(target, str(val_int))
                changed = True
        elif atype == "all_relay_off":
            for k in RELAY_KEYS:
                if self.relays[k] != "0":
                    self.relays[k] = "0"
                    db.update_device_status(k, "0")
                    changed = True
        elif atype == "all_relay_on":
            for k in RELAY_KEYS:
                if self.relays[k] != "1":
                    self.relays[k] = "1"
                    db.update_device_status(k, "1")
                    changed = True

        # 写告警记录 (模拟 bridge 的 create_alarm)
        msg = (f"规则「{act['rule_name']}」触发: {act['source_key']}={act['source_value']}"
               f", 已{('执行' if changed or atype=='send_alarm' else '状态无变化')}")
        try:
            db.create_alarm(
                rule_id=act.get("rule_id"),
                rule_name=act["rule_name"],
                source_key=act["source_key"],
                source_value=act["source_value"],
                level=act.get("alarm_level", "warning"),
                message=msg,
            )
            print(f"[fake] ⚠️ 告警: {msg}")
        except Exception as e:
            print(f"[fake] 告警写入失败: {e}")

    def run(self, interval=2.0):
        print(f"[fake] FakeBridge 启动, 每 {interval}s 上报一批模拟数据 (Ctrl+C 停止)")
        while True:
            self.step_once()
            if self.tick % 5 == 0:
                print(f"[fake] tick={self.tick} T={self.temperature} "
                      f"H={self.humidity} human={self.human} smoke={int(self.smoke)} "
                      f"relays={self.relays}")
            time.sleep(interval)


def main():
    db.init_db()
    fb = FakeBridge()
    if "--once" in sys.argv:
        fb.step_once()
        print("[fake] 单批模拟数据已写入")
    else:
        fb.run()


if __name__ == "__main__":
    main()
