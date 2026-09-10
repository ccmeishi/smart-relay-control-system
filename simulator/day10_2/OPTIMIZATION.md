# Day10.2 大屏优化清单

> 文档目的：把 Day10.2 大屏测试中发现的问题 + 修复方案整理成可执行清单，按优先级排序，便于 Trae Code 直接照着改。
>
> **优先级说明**：
> - 🔴 **P0**：必修，**阻塞演示效果**，必须改
> - 🟡 **P1**：重要，影响体验/可维护性
> - 🟢 **P2**：锦上添花，加分用
> - ⚪ **P3**：长远架构改进，下个迭代再做

---

## 总览（17 项）

| # | 优先级 | 问题 | 文件位置 |
|---|--------|------|---------|
| 1 | 🔴 P0 | App.vue 布局空洞（row 1 后两列空着） | `frontend/src/App.vue` |
| 2 | 🔴 P0 | device_status_history 写入太频繁（11万/h） | `backend/app.py:142-158` |
| 3 | 🔴 P0 | WebSocket device_status 推送抖动 | `backend/app.py:142-158` |
| 4 | 🟡 P1 | 告警面板无操作按钮（老师想演示 ack 卡住） | `frontend/src/components/AlarmPanel.vue` |
| 5 | 🟡 P1 | 在线率永远 100%（离线场景无视觉测试） | `backend/db.py` + `simulator/fake_bridge.py` |
| 6 | 🟡 P1 | 日志只有 print 没分级 | 全后端 |
| 7 | 🟡 P1 | SQLite 多线程并发可能 "database is locked" | `backend/db.py` |
| 8 | 🟡 P1 | `_sensor_stable` 进程内字典，backend 重启丢触发 | `backend/db.py` |
| 9 | 🟢 P2 | ChannelStatus 按钮 busy 状态可加 spinner | `frontend/src/components/ChannelStatus.vue` |
| 10 | 🟢 P2 | 键盘快捷键（F 全屏 / Esc 退出 / R 重连） | `frontend/src/App.vue` |
| 11 | 🟢 P2 | 大屏背景装饰动画（扫描线/呼吸光带/glow） | `frontend/src/style.css` |
| 12 | 🟢 P2 | 大屏时间显示毫秒 + "北京时间" 标签 | `frontend/src/App.vue` |
| 13 | 🟢 P2 | 告警列表超过 50 条应虚拟滚动 | `frontend/src/components/AlarmPanel.vue` |
| 14 | 🟢 P2 | "今日告警" 用全量不准 | `backend/api.py` + `AlarmPanel.vue` |
| 15 | ⚪ P3 | fake_bridge 异常退出没自动重启 | `backend/bridge_runner.py` |
| 16 | ⚪ P3 | MQTT 下发失败没回写 device_status 标记 | `backend/api.py` |
| 17 | ⚪ P3 | 没单元测试 | 新建 `backend/test_*.py` |

---

## 🔴 P0-1：App.vue 布局空洞（row 1 后两列空着）

### 问题描述
读 `App.vue:14-26` 看到 grid 布局：

```
DeviceOverview     ← 无 style，自动占 row 1 col 1
ChannelStatus      ← grid-column:1, grid-row:3
DataTrend          ← grid-column:2, grid-row:2/3（跨 row 2-3）
AlarmPanel         ← grid-column:3, grid-row:2
SceneRules + OnlineRate ← grid-column:3, grid-row:3
```

实际渲染：
- ✅ Row 1：只有 DeviceOverview 在最左
- ❌ **Row 1 col 2 / col 3 完全空着**
- ✅ Row 2-3：三列正常

**演示时大屏顶部右侧大片空白**，对老师非常尴尬。

### 修复方案

将左列改为 2 行布局（设备概览在上、通道状态在下），中列跨 2 列（数据趋势占中右两列大块），右列分 3 行（告警面板/场景联动/在线率）：

```vue
<template>
  <div class="dashboard">
    <!-- 头部 -->
    <header class="dash-header">...</header>

    <!-- 左列 -->
    <DeviceOverview class="cell" style="grid-column: 1; grid-row: 1;" />
    <ChannelStatus class="cell" style="grid-column: 1; grid-row: 2;" />

    <!-- 中右列 - 数据趋势占主视觉 -->
    <DataTrend class="cell" style="grid-column: 2; grid-row: 1/3;" />

    <!-- 右列 -->
    <AlarmPanel class="cell" style="grid-column: 3; grid-row: 1;" />
    <div class="cell" style="grid-column: 3; grid-row: 2; display: grid; grid-template-rows: 1fr 1fr; gap: 14px;">
      <SceneRules />
      <OnlineRate />
    </div>
  </div>
</template>
```

### 验收
- 浏览器打开大屏，**无任何空白单元格**
- 6 个模块都有内容显示

---

## 🔴 P0-2：device_status_history 写入太频繁

### 问题描述
**测试数据**：10 秒内 `device_status_history` 写入了 324 条（4 个采集点 × 81 次）。

**推算**：60 分钟保留窗口下会累计约 **11.6 万条**记录。SQLite 索引会膨胀，查询会变慢。

### 根因
`backend/app.py:142-158` 的 `_poll_status()`：
```python
for k, v in flat.items():
    if self.last_status.get(k) != v:
        db.record_history(k, v, source=self.source)  # ← 每次微小变化都写
        self.last_status[k] = v
        changed = True
```

fake_bridge 每 0.5-1s 让温度在 24.5 → 24.7 → 24.4 之间飘，每次都算"变化"。

### 修复方案（推荐：仪表采样）

**方案 C**：兼顾精度和频率 —— 30s 内同一 key 至少记 1 条，变化时立即记：

```python
class DataWatcher:
    def __init__(self, source: str):
        self.source = source
        self.last_status = {}
        self.last_history_ts = {}    # ← 新增：每 key 上次写历史的时间
        self.last_max_alarm_id = 0
        self.last_rule_counts = {}
        self._stop = threading.Event()

    def _poll_status(self):
        current = db.get_device_status_all()
        flat = {k: v["value"] for k, v in current.items()}
        now = time.time()
        for k, v in flat.items():
            prev = self.last_status.get(k)
            prev_ts = self.last_history_ts.get(k, 0)
            if prev != v:
                # 30s 节流：变化时也至少 30s 才记一条；首次变化立即记
                if prev is None or now - prev_ts >= 30:
                    db.record_history(k, v, source=self.source)
                    self.last_history_ts[k] = now
                self.last_status[k] = v
                changed = True
        # 删除已不存在的 key
        for k in list(self.last_status.keys()):
            if k not in flat:
                del self.last_status[k]
                changed = True
        if changed:
            hub.broadcast(EV_DEVICE_STATUS, flat)
```

### 验收
- 启动后观察 60 秒，`device_status_history` 新增条数 ≤ 8（4 key × 2 条 = 至多 8 条/min）
- 60 分钟保留窗口下总记录数 ≤ 480 条（而非 11 万）

---

## 🔴 P0-3：WebSocket device_status 推送抖动

### 问题描述
**测试观察**：5 秒内收到 14 条 WS 消息，其中 `device_status` 占 7 条。ECharts 折线和环形图肉眼可见的抖动。

### 根因
`_poll_status()` 0.5s 跑一次，每次状态变就立即 `hub.broadcast(EV_DEVICE_STATUS)`。

### 修复方案
在 DataWatcher 增加节流字段，**只对 `device_status` 事件做 1.5s 节流**，`relay_changed` 不节流（必须立即推用户操作反馈）：

```python
class DataWatcher:
    def __init__(self, source: str):
        # ... 原有字段 ...
        self._last_status_broadcast_ts = 0  # ← 新增

    def _poll_status(self):
        current = db.get_device_status_all()
        flat = {k: v["value"] for k, v in current.items()}
        now = time.time()
        # ... P0-2 的逻辑 ...
        # 只在 1.5s 间隔内推送 device_status
        if changed and now - self._last_status_broadcast_ts >= 1.5:
            hub.broadcast(EV_DEVICE_STATUS, flat)
            self._last_status_broadcast_ts = now
        # 但保留"立即初始化"：last_status_broadcast_ts == 0 时直接推
        elif changed and self._last_status_broadcast_ts == 0:
            hub.broadcast(EV_DEVICE_STATUS, flat)
            self._last_status_broadcast_ts = now
```

### 验收
- WS 客户端 5 秒观察期内 `device_status` 事件数 ≤ 4 条
- ECharts 折线和环形图视觉上无抖动
- 用户点继电器时 `relay_changed` 仍立即收到（< 200ms）

---

## 🟡 P1-4：告警面板无操作按钮

### 问题描述
`AlarmPanel.vue` 只渲染告警列表，没有"确认/清除"按钮。老师想现场演示 ack/clear 流程就卡住。

### 修复方案

**Step 1**：在 `backend/api.py` 增加 REST 端点（复用 Day10 的逻辑）：

```python
@bp.post("/alarms/<int:aid>/ack")
def alarm_ack(aid):
    db.acknowledge_alarm(aid, by='dashboard')
    return jsonify({"ok": True})

@bp.post("/alarms/ack-all")
def alarm_ack_all():
    n = db.acknowledge_all_alarms(by='dashboard')
    return jsonify({"ok": True, "count": n})

@bp.post("/alarms/clear-all")
def alarm_clear_all():
    n = db.clear_all_alarms()
    return jsonify({"ok": True, "count": n})
```

> ⚠️ 注意：当前 `db.clear_all_alarms()` 返回 `None`，需改成返回受影响行数。

**Step 2**：在 `frontend/src/api/http.js` 补充：

```js
ackAlarm: (id) => http.post(`/alarms/${id}/ack`),
ackAllAlarms: () => http.post('/alarms/ack-all'),
clearAllAlarms: () => http.post('/alarms/clear-all'),
```

**Step 3**：在 `frontend/src/stores/dashboard.js` 增加 actions：

```js
async ackAlarm(id) {
  await api.ackAlarm(id)
  // 本地立刻反映，后台轮询校正
  const target = this.recentAlarms.find((a) => a.id === id)
  if (target) target.status = 'acknowledged'
  this.pollAlarmStats()
},
async ackAllAlarms() {
  await api.ackAllAlarms()
  this.recentAlarms.forEach((a) => (a.status = 'acknowledged'))
  this.pollAlarmStats()
},
async clearAllAlarms() {
  await api.clearAllAlarms()
  this.recentAlarms.forEach((a) => (a.status = 'cleared'))
  this.pollAlarmStats()
},
```

**Step 4**：在 `AlarmPanel.vue` 增加操作按钮区（仅 admin 显示）：

```vue
<div class="alarm-actions">
  <button class="btn btn-warn" @click="store.ackAllAlarms">全部确认</button>
  <button class="btn btn-danger" @click="store.clearAllAlarms">全部清除</button>
</div>
```

### 验收
- 老师在大屏上点"全部确认" → 告警卡片状态变 acknowledged
- "全部清除" → 状态变 cleared
- 后端 SQLite `alarm_records.status` 列正确更新

---

## 🟡 P1-5：在线率永远 100%（离线场景无视觉测试）

### 问题描述
`db.get_overview()` 看 `device_status` 表有没有行，fake_bridge 一直在写 → 永远 100%。
老师若问"如果设备掉线了怎么办"，大屏无法演示。

### 修复方案

**Step 1**：定义"在线"语义（基于 `updated_at > now() - 60s`）：

```python
# backend/db.py
ONLINE_TIMEOUT_SEC = 60

def get_overview():
    conn = sqlite3.connect(DB_PATH)
    try:
        now = time.time()
        cutoff = now - ONLINE_TIMEOUT_SEC
        rows = conn.execute('''
            SELECT gateway_key, updated_at
            FROM device_status
            ORDER BY gateway_key
        ''').fetchall()
        total = len(rows)
        online = sum(1 for r in rows if r[1] and r[1] > cutoff)
        offline = total - online
        rate = (online / total * 100) if total > 0 else 100.0
        return {
            "total": total,
            "online": online,
            "offline": offline,
            "online_rate": round(rate, 1),
        }
    finally:
        conn.close()
```

**Step 2**：在 `fake_bridge.py` 增加"模拟断网"功能（演示按钮）：

```python
# simulator/fake_bridge.py
import threading

_network_simulation = {
    'paused_keys': set(),  # 暂停更新的 key 集合
    'pause_until': {}      # key → 解禁时间戳
}

def pause_key(key, seconds=30):
    """模拟某个采集点断网 N 秒."""
    _network_simulation['paused_keys'].add(key)
    _network_simulation['pause_until'][key] = time.time() + seconds

def step_once():
    # ... 在写入前检查 ...
    for k, v in new_values.items():
        if k in _network_simulation['paused_keys']:
            until = _network_simulation['pause_until'].get(k, 0)
            if time.time() < until:
                continue  # 跳过，不更新 device_status
            else:
                _network_simulation['paused_keys'].discard(k)
        # ... 正常更新 ...
```

**Step 3**：在 `ChannelStatus.vue` 的卡片右上角增加"断网指示灯"：

```vue
<div class="device-status">
  <span class="status-dot" :class="{ online: isOnline, offline: !isOnline }"></span>
  <span class="status-text">{{ isOnline ? '在线' : '已离线 ' + offlineSec + 's' }}</span>
</div>
```

### 验收
- 后台跑 `db.pause_key('temperature', 30)` → 30 秒内大屏在线率从 100% 掉到 87.5%（7/8）
- 30 秒后自动恢复 100%

---

## 🟡 P1-6：日志只有 print，没分级

### 问题描述
所有日志 `print(f"[watcher] ...") print(f"[api] ...")`，调试全靠 tail 日志。

### 修复方案

新建 `backend/log_setup.py`：

```python
import logging
import os

_LOG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'logs')
os.makedirs(_LOG_DIR, exist_ok=True)

def setup_logger(name='day102', level=logging.INFO):
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(level)
    fmt = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s.%(funcName)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    fh = logging.FileHandler(os.path.join(_LOG_DIR, 'day102.log'), encoding='utf-8')
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler()
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger

logger = setup_logger()
```

然后把所有 `print(f"[watcher] ...")` 改成 `logger.info("...")`，错误改成 `logger.error("...")`。

涉及文件：
- `backend/app.py`
- `backend/api.py`
- `backend/ws_hub.py`
- `backend/bridge_runner.py`
- `simulator/fake_bridge.py`

### 验收
- 启动后 `logs/day102.log` 持续输出带时间戳的日志
- `logger.error(...)` 输出到 stderr

---

## 🟡 P1-7：SQLite 多线程并发 → "database is locked" 风险

### 问题描述
DataWatcher daemon thread + Flask request threads 都直接 `import db` 调用，每次都新开连接。
没开 WAL 模式，没设 busy_timeout。

### 修复方案

在 `backend/db.py` 的 `init_db()` 末尾加：

```python
def init_db():
    # ... 原有建表逻辑 ...
    with conn:
        conn.execute("PRAGMA journal_mode=WAL")  # 读不阻塞写
        conn.execute("PRAGMA busy_timeout=5000")  # 5 秒锁等待
        conn.execute("PRAGMA synchronous=NORMAL")  # 性能/安全平衡
        # 热点表索引
        conn.execute("CREATE INDEX IF NOT EXISTS idx_dsh_key_time ON device_status_history(gateway_key, recorded_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alarms_triggered ON alarm_records(triggered_at)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_alarms_status ON alarm_records(status)")
```

### 验收
- 长时间运行（30 分钟以上）无 `database is locked` 异常
- `device_status_history` 按 (key, time) 查询 < 10ms

---

## 🟡 P1-8：`_sensor_stable` 进程内字典，backend 重启丢触发

### 问题描述
`bridge_runner` 切换瞬间、backend 重启瞬间，`_sensor_stable` 清空，首个评估直接丢弃。
稳定性逻辑无法跨进程保留。

### 修复方案
把稳定状态写到 SQLite：

**Step 1**：schema 迁移：

```python
def init_db():
    # ... 原有 ...
    cols = [r[1] for r in conn.execute("PRAGMA table_info(scene_rules)").fetchall()]
    if 'last_observed_value' not in cols:
        conn.execute("ALTER TABLE scene_rules ADD COLUMN last_observed_value TEXT")
    if 'last_observed_count' not in cols:
        conn.execute("ALTER TABLE scene_rules ADD COLUMN last_observed_count INTEGER DEFAULT 0")
```

**Step 2**：替换 `_sensor_stable` 为数据库版本：

```python
def evaluate_scene_rules(gateway_key, value):
    # ...
    rules = list_scene_rules_with_filter(gateway_key)
    now = time.time()

    for rule in rules:
        if not rule['enabled']:
            continue

        # 稳定状态检测
        STABLE_THRESHOLD = 3
        if rule['last_observed_value'] == str(value):
            new_count = rule['last_observed_count'] + 1
        else:
            new_count = 1

        # 持久化稳定状态
        conn.execute(
            'UPDATE scene_rules SET last_observed_value=?, last_observed_count=? WHERE id=?',
            (str(value), new_count, rule['id'])
        )
        conn.commit()

        if new_count < STABLE_THRESHOLD:
            continue  # 未达阈值，跳过

        # ... 原有触发逻辑 ...
```

### 验收
- backend 重启后第一次接收 temperature=40 → 第 1 次不触发
- 第 2 次仍不触发（数据库 count=1）
- 第 3 次触发（count=3）
- 数据库重启后值仍保留

---

## 🟢 P2-9：ChannelStatus 按钮 busy 状态可加 spinner

### 修复
`frontend/src/components/ChannelStatus.vue` 第 6-21 行的 button 内增加 spinner SVG：

```vue
<button v-for="r in relays" :key="r.key" class="relay-btn"
  :class="{ on: isOn(r.key), disabled: busy === r.key }"
  :disabled="busy === r.key"
  @click="onToggle(r.key)">
  <svg v-if="busy === r.key" class="spinner" viewBox="0 0 24 24">
    <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor"
      stroke-width="3" stroke-dasharray="40 20"/>
  </svg>
  <svg v-else viewBox="0 0 24 24" class="relay-icon">
    <path :fill="isOn(r.key) ? '#67c23a' : '#5a6678'"
      d="M12 2a7 7 0 0 0-7 7v6a3 3 0 0 0 3 3h8a3 3 0 0 0 3-3V9a7 7 0 0 0-7-7zm-3 7a1 1 0 0 1 1-1h4a1 1 0 1 1 0 2h-4a1 1 0 0 1-1-1z"/>
  </svg>
  <div class="relay-name">{{ r.name }}</div>
  <div class="relay-state">{{ busy === r.key ? '下发中' : (isOn(r.key) ? 'ON' : 'OFF') }}</div>
</button>
```

CSS：
```css
.spinner { width: 34px; height: 34px; animation: spin 0.8s linear infinite; color: #6db3ff; }
@keyframes spin { from { transform: rotate(0); } to { transform: rotate(360deg); } }
```

---

## 🟢 P2-10：键盘快捷键

### 修复
在 `frontend/src/App.vue` 的 `onMounted` 中增加：

```js
function onKeydown(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
  switch (e.key.toLowerCase()) {
    case 'f':
      if (!document.fullscreenElement) document.documentElement.requestFullscreen()
      else document.exitFullscreen()
      break
    case 'escape':
      if (document.fullscreenElement) document.exitFullscreen()
      break
    case 'r':
      wsClient && wsClient.close()
      wsClient = new WsClient(...)
      wsClient.connect()
      console.log('[hotkey] WS 重连')
      break
  }
}
onMounted(() => {
  // ...
  document.addEventListener('keydown', onKeydown)
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKeydown)
  // ...
})
```

---

## 🟢 P2-11：大屏背景装饰动画

### 修复
在 `frontend/src/style.css` 增加：

```css
.dashboard {
  position: relative;
  background:
    radial-gradient(ellipse at 20% 20%, rgba(64,158,255,0.08) 0%, transparent 50%),
    radial-gradient(ellipse at 80% 80%, rgba(103,194,58,0.06) 0%, transparent 50%),
    #050816;
}

/* 扫描线动画 */
.dashboard::before {
  content: '';
  position: absolute; inset: 0;
  background: linear-gradient(180deg,
    transparent 0%,
    rgba(64,158,255,0.05) 50%,
    transparent 100%);
  background-size: 100% 4px;
  animation: scan 8s linear infinite;
  pointer-events: none;
  z-index: 1;
}
@keyframes scan {
  from { background-position: 0 -100%; }
  to   { background-position: 0 200%; }
}

/* header 呼吸光带 */
.dash-header::after {
  content: '';
  position: absolute; bottom: 0; left: 0; right: 0; height: 1px;
  background: linear-gradient(90deg, transparent, #409eff, transparent);
  animation: breathe 3s ease-in-out infinite;
}
@keyframes breathe {
  0%, 100% { opacity: 0.4; }
  50% { opacity: 1; }
}
```

---

## 🟢 P2-12：大屏时间显示毫秒 + 北京时间

### 修复
`frontend/src/App.vue:48-53` 的 `updateClock`：

```js
function updateClock() {
  const d = new Date()
  const p = (n, len = 2) => String(n).padStart(len, '0')
  clock.value = `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ` +
                `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(),3)} 北京时间`
}
```

---

## 🟢 P2-13：告警列表超过 50 条应虚拟滚动

### 修复
当前 `recentAlarms` 限制 20 条，无需虚拟滚动。
但若老师演示产生 100+ 告警，渲染会卡。

**简单方案**：直接把上限改为 50，超出不分页（避免复杂依赖）。
**进阶方案**：引入 `vue-virtual-scroller`，只渲染可见窗口。

---

## 🟢 P2-14："今日告警" 用全量不准

### 修复

**Step 1**：后端加 `/api/alarm-stats/today`：

```python
@bp.get("/alarm-stats/today")
def alarm_stats_today():
    conn = sqlite3.connect(db.DB_PATH)
    try:
        rows = conn.execute('''
            SELECT level, status, COUNT(*)
            FROM alarm_records
            WHERE triggered_at >= date('now', 'start of day')
            GROUP BY level, status
        ''').fetchall()
    finally:
        conn.close()
    return jsonify({"by_level": dict((r[0], r[2]) for r in rows if r[1] == 'active')})
```

**Step 2**：前端 `AlarmPanel.vue` 第 1 个卡片改用 today 数据：

```vue
<div class="alarm-stat">
  <div class="num big-num">{{ todayCount }}</div>
  <div class="lbl">今日告警</div>
</div>
```

---

## ⚪ P3-15：fake_bridge 异常退出没自动重启

### 修复
`backend/bridge_runner.py` 增加 watchdog：

```python
import time
import threading

class BridgeRunner:
    def __init__(self, cmd):
        self.cmd = cmd
        self.proc = None
        self._stop = threading.Event()
        self._restart_count = 0
        self._max_restart = 3

    def start(self):
        self._spawn()
        threading.Thread(target=self._watchdog, daemon=True).start()

    def _spawn(self):
        self.proc = subprocess.Popen(self.cmd, ...)
        self._restart_count = 0

    def _watchdog(self):
        while not self._stop.is_set():
            if self.proc.poll() is not None:
                # 进程异常退出
                if self._restart_count < self._max_restart:
                    logger.warning(f"bridge 异常退出, 自动重启 ({self._restart_count+1}/{self._max_restart})")
                    self._spawn()
                    self._restart_count += 1
                else:
                    logger.error("bridge 连续异常, 已达最大重启次数")
                    break
            self._stop.wait(2)
```

---

## ⚪ P3-16：MQTT 下发失败没回写 device_status 标记

### 修复
`backend/api.py:55-73` 的 `_publish_relay_write`：

```python
def _publish_relay_write(props: dict) -> bool:
    client = _get_mqtt_client()
    if client is None:
        return False
    cfg = db.load_gateway_config()
    topic = f"{cfg['product_id']}/{cfg['device_id']}/properties/write"
    payload = {"timestamp": int(time.time()*1000),
               "messageId": f"dashboard-{int(time.time()*1000)}",
               "properties": props}
    try:
        msg_info = client.publish(topic, json.dumps(payload), qos=1)
        msg_info.wait_for_publish(timeout=2)  # 阻塞等待 broker ACK
        if msg_info.is_published():
            return True
        return False
    except Exception as e:
        logger.error(f"MQTT 下发失败: {e}")
        return False

@bp.post("/devices/toggle")
def devices_toggle():
    body = request.get_json(silent=True) or {}
    key = str(body.get("key", "")).strip()
    value = str(body.get("value", "")).strip()
    if key not in RELAY_KEYS:
        return jsonify({"ok": False, "error": "..."}), 400
    if value not in ("0", "1"):
        return jsonify({"ok": False, "error": "..."}), 400

    # 1. 先下发 MQTT, 失败不写库
    published = _publish_relay_write({key: int(value)})
    if not published:
        return jsonify({"ok": False, "error": "MQTT 下发失败, 设备可能离线"}), 503

    # 2. 成功才写 device_status
    db.update_device_status(key, value)
    # ... 广播 WS ...
    return jsonify({"ok": True, "mqtt_published": True})
```

---

## ⚪ P3-17：没单元测试

### 新建测试

`backend/test_db.py`：
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'simulator', 'day10_2', 'backend'))
import db
import tempfile

def setup_module(module):
    db.DB_PATH = os.path.join(tempfile.mkdtemp(), 'test.db')
    db.init_db()

def test_evaluate_scene_rules_basic():
    acts = db.evaluate_scene_rules('temperature', '40')
    assert isinstance(acts, list)

def test_get_overview_empty():
    db.cleanup_all()  # 清空
    ov = db.get_overview()
    assert ov['total'] == 0
    assert ov['online_rate'] == 100.0
```

`backend/test_api.py`：
```python
import json
from app import app

def test_toggle_invalid():
    client = app.test_client()
    r = client.post('/api/devices/toggle', json={'key': 'relay9', 'value': '1'})
    assert r.status_code == 400

def test_toggle_ok():
    client = app.test_client()
    r = client.post('/api/devices/toggle', json={'key': 'relay1', 'value': '1'})
    assert r.status_code in (200, 503)  # 503 表示 MQTT 不可达
```

运行：`cd simulator/day10_2 && python -m pytest backend/test_*.py -v`

---

## 🎯 推荐执行顺序

按优先级从高到低顺序执行：

1. **先做 P0**（必修）：P0-1 布局空洞 → P0-2 历史节流 → P0-3 WS 推送节流
2. **再做 P1**（重要）：P1-4 告警操作 → P1-5 离线视觉 → P1-6 logging → P1-7 SQLite WAL → P1-8 规则状态持久
3. **P2**（加分）：按需做 P2-9 ~ P2-14
4. **P3**（长远）：作为下个迭代，本次不强制

> 核心目标：**先保证老师演示时不出现空白/卡顿/抖动**，P0 全部 + P1-4/P1-5 是演示的最低门槛。

---

## ✅ 完成后输出

每完成一项，在对应章节末尾追加：
```
✅ 完成时间: YYYY-MM-DD HH:MM
   Commit:  <git commit short hash>
   验收:    <通过/部分通过/未通过 + 说明>
```

全部完成后总结 `git log --oneline simulator/day10_2/` 输出给我，方便追踪。