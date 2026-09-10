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
_BACKEND_DIR = os.path.dirname(_HERE)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

from log_setup import logger
import db

RELAY_KEYS = ["relay1", "relay2", "relay3", "relay4"]


class FakeBridge:
    """模拟网关: 维护一组缓慢漂移的传感器值 + 继电器状态."""

    # P1-5: 演示离线场景用的传感器 key (不含继电器, 继电器由场景规则/用户控制)
    SENSOR_KEYS = ("temperature", "humidity", "human", "smoke")

    def __init__(self):
        self.temperature = 26.0
        self.humidity = 55.0
        self.human = 1
        self.smoke = 8
        self.relays = {k: "0" for k in RELAY_KEYS}
        self.relays["relay2"] = "1"  # 默认灯开
        self.tick = 0
        # P1-5: 断网模拟. paused_until[key] = epoch, 该 key 在此时间前不写库 (模拟掉线)
        self.paused_until = {}
        # 问题2b: 异常事件模拟. 偶发让温度/烟雾冲高越过 critical 阈值(35/50),
        # 使"高温自动断电""烟雾告警联动"等严重场景规则能真实触发, 大屏可演示联动+告警.
        # anomaly = {'key','peak','until'} 或 None
        self.anomaly = None

    def _maybe_start_anomaly(self):
        """每 ~60 tick (约 120 秒) 判定一次, 概率触发一次持续 10 tick (~20s) 的异常冲高.

        温度冲高到 37 (>35 触发高温自动断电, 全关继电器)
        烟雾冲高到 62 (>50 触发烟雾告警联动)
        """
        if self.anomaly is None and self.tick > 0 and self.tick % 60 == 0 \
                and random.random() < 0.6:
            if random.random() < 0.5:
                self.anomaly = {"key": "temperature", "peak": 37.0, "until": self.tick + 10}
                logger.info("[fake][异常] 温度冲高 -> 演示「高温自动断电」")
            else:
                self.anomaly = {"key": "smoke", "peak": 62.0, "until": self.tick + 10}
                logger.info("[fake][异常] 烟雾冲高 -> 演示「烟雾告警联动」")

    def _maybe_pause_random_sensor(self):
        """每 ~40 个 tick (约 80 秒) 随机让一个传感器断网 75 秒, 演示离线场景.

        在线判定阈值是 60 秒 (db.py get_overview), 所以断网时长必须 > 60 秒,
        该通道才会真正在大屏上变成"离线"(在线率 8/8 -> 7/8=87.5%),
        恢复上报后自动回到在线.
        """
        if self.tick % 40 == 0 and self.tick > 0:
            key = random.choice(self.SENSOR_KEYS)
            self.paused_until[key] = time.time() + 75
            logger.info(f"[fake][断网] 模拟 {key} 断网 75 秒 (>60s 在线阈值, 大屏将显示该通道离线)")

    def _is_paused(self, key):
        """检查 key 是否处于断网期"""
        until = self.paused_until.get(key)
        if until is None:
            return False
        if time.time() < until:
            return True
        # 过期, 清除
        del self.paused_until[key]
        return False

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
        self._maybe_pause_random_sensor()  # P1-5: 随机触发断网
        self._maybe_start_anomaly()        # 问题2b: 随机触发异常冲高

        # 1. 传感器漂移
        # 异常期: 对应传感器快速向峰值爬升(越过 critical 阈值), 其余正常漂移
        # 非异常期: 全部正常随机游走; 异常刚结束时高值由 _drift 边界回弹自然回落
        in_anomaly = self.anomaly is not None and self.tick < self.anomaly["until"]
        if in_anomaly:
            a = self.anomaly
            if a["key"] == "temperature":
                self.temperature = round(min(a["peak"], self.temperature + 1.8), 1)
                self.smoke = self._drift(self.smoke, 3.0, 20.0, 1.2)
            else:  # smoke
                self.smoke = round(min(a["peak"], self.smoke + 9.0), 1)
                self.temperature = self._drift(self.temperature, 24.0, 31.0, 0.4)
        else:
            if self.anomaly is not None:  # 异常刚结束
                logger.info(f"[fake][异常] {self.anomaly['key']} 恢复正常范围")
                self.anomaly = None
            self.temperature = self._drift(self.temperature, 24.0, 31.0, 0.4)
            self.smoke = self._drift(self.smoke, 3.0, 20.0, 1.2)
        self.humidity = self._drift(self.humidity, 45.0, 68.0, 0.8)
        # 人体感应: 大部分时间保持, 每 ~20 个周期有机会翻转
        if random.random() < 0.06:
            self.human = 1 - self.human

        # 2. 写 device_status (模拟网关上报). P1-5: 断网期间跳过对应 key
        sensor_vals = (("temperature", str(self.temperature)),
                       ("humidity", str(self.humidity)),
                       ("human", str(self.human)),
                       ("smoke", str(int(self.smoke))))
        for key, val in sensor_vals:
            if not self._is_paused(key):
                db.update_device_status(key, val)
        for k in RELAY_KEYS:
            db.update_device_status(k, self.relays[k])

        # 3. 评估场景规则 (对每个传感器 key), 模拟 bridge 的规则引擎
        for key, val in sensor_vals:
            if self._is_paused(key):
                continue  # 断网期间不评估规则
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
            logger.info(f"[fake][告警] {msg}")
        except Exception as e:
            logger.error(f"[fake] 告警写入失败: {e}")

    def run(self, interval=2.0):
        logger.info(f"[fake] FakeBridge 启动, 每 {interval}s 上报一批模拟数据 (Ctrl+C 停止)")
        while True:
            self.step_once()
            if self.tick % 5 == 0:
                logger.info(f"[fake] tick={self.tick} T={self.temperature} "
                            f"H={self.humidity} human={self.human} smoke={int(self.smoke)} "
                            f"relays={self.relays}")
            time.sleep(interval)


def main():
    db.init_db()
    fb = FakeBridge()
    if "--once" in sys.argv:
        fb.step_once()
        logger.info("[fake] 单批模拟数据已写入")
    else:
        fb.run()


if __name__ == "__main__":
    main()
