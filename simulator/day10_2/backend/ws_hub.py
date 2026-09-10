"""WebSocket Hub — 维护大屏 WS 连接, 提供事件广播.

Bridge 子进程无法直接调用 Flask 进程内的 hub, 因此:
  - Bridge 只负责写 SQLite (device_status / alarm_records)
  - Flask 后台轮询线程检测到数据变化后, 调用 hub.broadcast() 推给前端

事件类型:
  device_status   设备状态全量变化
  alarm_new       新告警产生
  rule_triggered  场景规则触发
  relay_changed   继电器状态变化 (大屏点击下发后)
  history_tick    定时推送折线图最新点
  overview_tick   定时推送设备概览统计
"""
import json
import threading
import time


# 事件类型常量
EV_DEVICE_STATUS = "device_status"
EV_ALARM_NEW = "alarm_new"
EV_RULE_TRIGGERED = "rule_triggered"
EV_RELAY_CHANGED = "relay_changed"
EV_HISTORY_TICK = "history_tick"
EV_OVERVIEW_TICK = "overview_tick"


class WsHub:
    """线程安全的 WebSocket 连接池 + 广播器."""

    def __init__(self):
        self.clients = set()
        self._lock = threading.Lock()

    def register(self, ws):
        with self._lock:
            self.clients.add(ws)
        print(f"[ws] 大屏已连接, 当前连接数: {len(self.clients)}")

    def unregister(self, ws):
        with self._lock:
            self.clients.discard(ws)
        print(f"[ws] 大屏断开, 当前连接数: {len(self.clients)}")

    @property
    def client_count(self) -> int:
        with self._lock:
            return len(self.clients)

    def broadcast(self, event_type: str, data: dict) -> int:
        """向所有大屏客户端推送事件, 返回成功送达的连接数.

        自动剔除发送失败(已断开)的连接.
        """
        msg = json.dumps({"type": event_type, "data": data, "ts": time.time()},
                         ensure_ascii=False, default=str)
        dead = []
        with self._lock:
            targets = list(self.clients)
        sent = 0
        for ws in targets:
            try:
                ws.send(msg)
                sent += 1
            except Exception:
                dead.append(ws)
        if dead:
            with self._lock:
                for ws in dead:
                    self.clients.discard(ws)
        return sent


# 全局单例 (app.py / api.py / 后台轮询线程共用)
hub = WsHub()
