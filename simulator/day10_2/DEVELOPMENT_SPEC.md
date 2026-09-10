# Day10.2 智慧物联网平台 - 大屏可视化 + 全链路联调 开发规格

> 本文档是 Day10.2 大屏展示功能的完整开发规格。发送给 Trae Code 实现，实现完成后由开发者本人（用户）执行测试验收。

---

## 1. 项目背景

### 1.1 任务来源
带教欧阳群刚老师布置的"Day 10 大屏 + 全链路联调 + 项目总结"任务。本规格**只覆盖大屏与全链路联调**部分，项目文档（README/物模型/接口文档/总结报告）不在本期范围。

### 1.2 核心目标
构建一个**Vue3 + ECharts + WebSocket 实时大屏**，完整展示"设备 → 网关 → 平台 → 大屏"全链路闭环：
- 实时反映设备状态（不写死静态数据）
- 支持点击大屏按钮控制设备（验证下行链路）
- 通过 WebSocket 推送告警/状态变化（验证上行链路）
- 数据来源优先真实 Bridge，缺失时回退到脚本模拟

### 1.3 与已有项目的关系
- 复用：`simulator/day10/db.py`、`simulator/day10/gateway_bridge.py` 的接口规范与表结构
- 独立：本期使用**独立 SQLite 数据库** `simulator/day10_2/iot_platform.db`，不污染 Day10 数据
- 衔接：通过 REST API + 文件级数据桥（device_status_history 表）衔接

---

## 2. 技术栈选型

| 层级 | 选型 | 理由 |
|------|------|------|
| 前端框架 | Vue 3.4+ + Composition API | 老师参考图明确要求 Vue3 |
| 前端构建 | Vite 5+ | 启动快、配置少 |
| 图表库 | ECharts 5.4+ | 老师参考图明确要求 |
| 状态管理 | Pinia 2+ | Vue3 官方推荐，比 Vuex 简洁 |
| HTTP | axios 1+ | Vue3 生态标配 |
| WebSocket | 原生 WebSocket | 不引入 socket.io，简单可控 |
| 后端 | Flask 3+ | 与 Day9/Day10 一致 |
| WebSocket 库 | flask-sock | 纯 Python，无需 eventlet/gevent |
| 数据库 | SQLite 3 | 与 Day9/Day10 一致 |
| Bridge | 复用 day10/gateway_bridge.py | 不重写 |

**禁止引入**：TypeScript（增加构建复杂度）；Tailwind（保持原生 CSS）；任何 UI 组件库（Element Plus/Ant Design 等）。

---

## 3. 目录结构

```
simulator/day10_2/
├── README.md                       # 简要运行说明
├── start_all.bat                   # 一键启动脚本
├── backend/
│   ├── __init__.py
│   ├── app.py                      # Flask 入口 + REST + WebSocket 路由
│   ├── db.py                       # SQLite 操作 + 初始化（含 device_status_history 表）
│   ├── ws_hub.py                   # WebSocket Hub（事件广播）
│   ├── api.py                      # 5 个 REST 接口
│   └── bridge_runner.py            # 启动 + 监控 Bridge 进程
├── bridge/
│   └── gateway_bridge.py           # 从 ../day10/ 复制过来（如有改动需注释）
├── simulator/
│   ├── modbus_slave_sim.py         # 从 ../day10/ 复制（如有改动需注释）
│   └── fake_bridge.py              # Bridge 数据回退模拟脚本
├── frontend/
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── main.js
│       ├── App.vue                 # 大屏整体布局
│       ├── style.css               # 全局深色科技风样式
│       ├── api/
│       │   ├── http.js             # axios 实例 + REST 方法
│       │   └── ws.js               # WebSocket 客户端（自动重连）
│       ├── stores/
│       │   └── dashboard.js        # Pinia 状态：设备/告警/规则
│       └── components/
│           ├── DeviceOverview.vue   # ① 设备概览
│           ├── ChannelStatus.vue   # ② 通道状态
│           ├── AlarmPanel.vue      # ③ 告警信息
│           ├── DataTrend.vue       # ④ 数据趋势
│           ├── SceneRules.vue      # ⑤ 场景联动
│           └── OnlineRate.vue      # ⑥ 设备在线率
└── logs/                           # 启动日志（git ignore）
```

---

## 4. 数据库设计

### 4.1 复用 Day10 表结构
完整复制 day10/db.py 的建表语句与种子数据初始化逻辑，保持以下表不变：
- `users`、`login_sessions`、`device_mappings`、`device_status`、`scene_rules`、`alarm_records`

### 4.2 新增表

```sql
-- 设备状态历史（时序数据，给大屏"数据趋势"模块用）
CREATE TABLE IF NOT EXISTS device_status_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    gateway_key TEXT NOT NULL,        -- e.g. 'relay1', 'temperature'
    value TEXT NOT NULL,              -- 字符串存储（兼容 ON/OFF 和数字）
    recorded_at TEXT NOT NULL,        -- ISO8601 UTC
    source TEXT DEFAULT 'bridge'      -- 'bridge' | 'simulator'
);
CREATE INDEX IF NOT EXISTS idx_history_key_time
    ON device_status_history(gateway_key, recorded_at DESC);

-- 大屏配置（动态调整刷新间隔、保留时长等）
CREATE TABLE IF NOT EXISTS dashboard_config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
INSERT OR IGNORE INTO dashboard_config(key, value, updated_at) VALUES
    ('history_retention_minutes', '60', datetime('now')),
    ('ws_broadcast_interval_ms', '500', datetime('now')),
    ('overview_poll_interval_ms', '5000', datetime('now'));
```

### 4.3 数据保留策略
- `device_status_history` 启动时清理 `recorded_at < now - retention_minutes` 的旧数据
- 默认保留 60 分钟，可在 `dashboard_config` 表中调整

---

## 5. 后端实现规格

### 5.1 Flask 应用（backend/app.py）

**启动参数**：
- 端口 `8081`（与 Day10 区分使用 `8083`，避免端口冲突；最终拍板：`8083`）
- 开启 WebSocket
- 注册 REST 蓝图与 WS Hub

**关键代码结构**：
```python
from flask import Flask, render_template, send_from_directory
from flask_sock import Sock
import db
from api import bp as api_bp
from ws_hub import WsHub

app = Flask(__name__, static_folder='../frontend/dist', static_url_path='/')
sock = Sock(app)
hub = WsHub()

app.register_blueprint(api_bp, url_prefix='/api')

@sock.route('/ws/dashboard')
def ws_endpoint(ws):
    hub.register(ws)
    try:
        while True:
            msg = ws.receive()  # 仅维持连接，不处理客户端消息
    except Exception:
        pass
    finally:
        hub.unregister(ws)

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

# SPA fallback：所有非 /api/* 路径都返回 index.html
@app.route('/<path:path>')
def spa(path):
    if path.startswith('api/'):
        return  # 404
    return send_from_directory(app.static_folder, 'index.html')
```

### 5.2 WebSocket Hub（backend/ws_hub.py）

**职责**：维护连接列表，提供广播方法。

**接口**：
```python
class WsHub:
    def __init__(self): self.clients: set = set()
    def register(self, ws): self.clients.add(ws)
    def unregister(self, ws): self.clients.discard(ws)
    def broadcast(self, event_type: str, data: dict):
        """向所有客户端推送事件，自动剔除已断开的连接"""
        msg = json.dumps({"type": event_type, "data": data, "ts": time.time()})
        dead = []
        for ws in list(self.clients):
            try: ws.send(msg)
            except Exception: dead.append(ws)
        for ws in dead: self.clients.discard(ws)
```

**事件类型常量**：
- `device_status`：设备状态变化
- `alarm_new`：新告警产生
- `rule_triggered`：场景规则触发
- `relay_changed`：继电器状态变化
- `history_tick`：定时推送最新历史点（折线图增量）

### 5.3 REST 接口（backend/api.py）

所有接口前缀 `/api`，返回 JSON。

| 方法 | 路径 | 说明 | 响应示例 |
|------|------|------|---------|
| GET | `/overview` | 设备概览 + 在线率 | `{"total": 8, "online": 7, "offline": 1, "online_rate": 87.5}` |
| GET | `/device-status` | 设备实时状态 | `{"relay1": "1", "temperature": "28.5", ...}` |
| GET | `/alarm-stats` | 告警统计 | `{"total": 5, "active": 2, "acknowledged": 2, "cleared": 1, "by_level": {"info":1,"warning":3,"critical":1}}` |
| GET | `/alarms/recent?limit=10` | 最近告警列表 | `[{"id":5,"level":"critical","message":"...","triggered_at":"..."}]` |
| GET | `/scene-rules` | 场景规则列表 | `[{"id":1,"name":"高温自动断电","trigger_count":3,"enabled":1}]` |
| GET | `/history/<gateway_key>?minutes=30` | 某采集点历史 | `[{"value":"28.5","recorded_at":"..."}]` |
| POST | `/devices/toggle` | 继电器控制 | `{"key":"relay1","value":"1"}` → 200 |

**POST /devices/toggle 行为**：
1. 校验 key ∈ {relay1, relay2, relay3, relay4}, value ∈ {"0","1"}
2. 写 `device_status` 表
3. **调用 bridge** 发 MQTT 下发（参考 day10/gateway_bridge.py 的实现）
4. 通过 `hub.broadcast("relay_changed", {...})` 推 WS

### 5.4 Bridge Runner（backend/bridge_runner.py）

**职责**：作为子进程启动 `bridge/gateway_bridge.py`，监控其存活，崩溃时自动重启。

**关键逻辑**：
```python
import subprocess, time, signal, os, sys

class BridgeRunner:
    def __init__(self, script_path: str):
        self.script_path = script_path
        self.proc = None
        self.should_run = True

    def start(self):
        self.proc = subprocess.Popen(
            [sys.executable, '-u', self.script_path],
            stdout=open('../logs/bridge.log', 'a'),
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(self.script_path)
        )
        print(f'[bridge] started pid={self.proc.pid}')

    def watch(self):
        while self.should_run:
            if self.proc is None or self.proc.poll() is not None:
                print('[bridge] dead, restarting...')
                self.start()
            time.sleep(5)

    def stop(self):
        self.should_run = False
        if self.proc: self.proc.terminate()
```

**集成到 app.py 启动**：
```python
if __name__ == '__main__':
    runner = BridgeRunner('../bridge/gateway_bridge.py')
    runner.start()
    try:
        app.run(host='0.0.0.0', port=8083, debug=False, threaded=True)
    finally:
        runner.stop()
```

### 5.5 数据采集策略（写入历史表）

**触发点 1**：当 `device_status` 表任一 key 的 value 发生变化时，写入 `device_status_history`。
**触发点 2**：当场景规则触发时，写入告警记录 + WS 推送。
**触发点 3**：每 30 秒执行清理：删除 `recorded_at < now - retention_minutes` 的旧数据。

**实现位置**：在 `db.py` 中提供 `record_history(key, value, source)` 函数。

---

## 6. 前端实现规格

### 6.1 整体布局（App.vue）

**布局方式**：CSS Grid，1920×1080 设计稿，自适应缩放。

```
┌──────────────────────────────────────────────────────────────┐
│  Header: 智慧物联网平台     当前时间        在线状态         │
├────────────┬──────────────────────────────┬─────────────────┤
│            │                              │                 │
│  ① 设备     │       ④ 数据趋势             │   ③ 告警信息    │
│  概览       │      (ECharts 折线)          │                 │
│            │                              │                 │
├────────────┼──────────────────────────────┼─────────────────┤
│            │                              │                 │
│  ② 通道    │       ⑤ 场景联动              │   ⑥ 设备       │
│  状态      │      (4 卡片)                │   在线率        │
│  (4 路)   │                              │   (环形图)      │
│            │                              │                 │
└────────────┴──────────────────────────────┴─────────────────┘
```

**CSS Grid 定义**：
```css
.dashboard {
    display: grid;
    grid-template-columns: 360px 1fr 360px;
    grid-template-rows: 80px 1fr 1fr;
    gap: 16px;
    height: 100vh;
    background: linear-gradient(135deg, #0a0e27 0%, #050816 100%);
    color: #e0e6ed;
    font-family: 'Microsoft YaHei', sans-serif;
}
```

### 6.2 全局样式（src/style.css）

**深色科技风主基调**：
- 背景：`#0a0e27` 到 `#050816` 渐变
- 卡片背景：`rgba(16, 28, 56, 0.6)` + `backdrop-filter: blur(8px)`
- 边框：`1px solid rgba(64, 158, 255, 0.3)`
- 主色：`#409eff`（蓝）、`#67c23a`（绿/在线）、`#e6a23c`（橙/警告）、`#f56c6c`（红/严重）
- 字体：`Microsoft YaHei` / `DIN` / `Orbitron`
- 标题前缀：每个模块标题前加一个发光的小圆点 + 文字

### 6.3 HTTP 客户端（src/api/http.js）

```javascript
import axios from 'axios'
const http = axios.create({ baseURL: '/api', timeout: 5000 })
http.interceptors.response.use(r => r.data, e => {
    console.error('[http]', e.config?.url, e.message)
    return Promise.reject(e)
})
export default {
    overview: () => http.get('/overview'),
    deviceStatus: () => http.get('/device-status'),
    alarmStats: () => http.get('/alarm-stats'),
    recentAlarms: (limit = 10) => http.get(`/alarms/recent?limit=${limit}`),
    sceneRules: () => http.get('/scene-rules'),
    history: (key, minutes = 30) => http.get(`/history/${key}?minutes=${minutes}`),
    toggleRelay: (key, value) => http.post('/devices/toggle', { key, value })
}
```

### 6.4 WebSocket 客户端（src/api/ws.js）

**关键特性**：
- 自动重连（指数退避：1s → 2s → 4s → 8s → 最大 30s）
- 断线提示
- 事件分发（Pinia action 调用）

```javascript
class WsClient {
    constructor(url, onEvent) {
        this.url = url
        this.onEvent = onEvent
        this.ws = null
        this.retry = 0
        this.shouldRun = true
    }
    connect() {
        this.ws = new WebSocket(this.url)
        this.ws.onopen = () => { this.retry = 0; console.log('[ws] connected') }
        this.ws.onmessage = (e) => {
            try { this.onEvent(JSON.parse(e.data)) }
            catch (err) { console.error('[ws] parse error', err) }
        }
        this.ws.onclose = () => {
            if (!this.shouldRun) return
            const delay = Math.min(30000, 1000 * Math.pow(2, this.retry++))
            console.log(`[ws] reconnect in ${delay}ms`)
            setTimeout(() => this.connect(), delay)
        }
        this.ws.onerror = (e) => console.error('[ws] error', e)
    }
    close() { this.shouldRun = false; this.ws?.close() }
}
```

### 6.5 Pinia Store（src/stores/dashboard.js）

```javascript
import { defineStore } from 'pinia'
export const useDashboardStore = defineStore('dashboard', {
    state: () => ({
        overview: { total: 0, online: 0, offline: 0, online_rate: 0 },
        deviceStatus: {},          // { relay1: '1', temperature: '28.5', ... }
        alarmStats: { total: 0, active: 0, acknowledged: 0, cleared: 0 },
        recentAlarms: [],          // 最新告警数组
        sceneRules: [],            // 场景规则数组
        history: {                 // 折线图历史数据
            temperature: [],
            humidity: [],
            human:     [],
            smoke:     []
        },
        wsConnected: false
    }),
    actions: {
        applyEvent(event) {
            switch (event.type) {
                case 'device_status': this.deviceStatus = event.data; break
                case 'alarm_new': this.recentAlarms.unshift(event.data); break
                case 'rule_triggered':
                    const r = this.sceneRules.find(x => x.id === event.data.id)
                    if (r) r.trigger_count = event.data.trigger_count
                    break
                case 'history_tick':
                    Object.assign(this.history, event.data)
                    break
            }
        }
    }
})
```

### 6.6 六个模块详细规格

#### ① DeviceOverview.vue（设备概览）

**布局**：
- 顶部数字大字号（设备总数 48px）
- 三个并排卡片：总数 / 在线 / 离线
- 底部进度条显示在线率

**数据来源**：`store.overview`（5 秒轮询一次 `/api/overview`）

**视觉**：数字使用 `Orbitron` 等宽字体，发光效果。

#### ② ChannelStatus.vue（通道状态）

**布局**：
- 2×2 网格，4 个大按钮
- 每个按钮：继电器图标（SVG）+ 名称 + ON/OFF 状态指示
- 点击切换 → 调用 `http.toggleRelay(key, newValue)` → 后端下发 MQTT + WS 广播

**交互细节**：
- ON 状态：绿色发光 + "ON" 文字
- OFF 状态：灰色 + "OFF" 文字
- 点击瞬间按钮有按下动画，500ms 内禁用避免重复点击

**实时更新**：监听 WS `relay_changed` 和 `device_status` 事件同步状态。

#### ③ AlarmPanel.vue（告警信息）

**布局**：
- 顶部 3 个统计卡片：今日告警 / 未处理 / 已处理
- 中部 1 个饼图（ECharts）：按 level 分布（info/warning/critical）
- 底部滚动列表：最近 10 条告警，新告警从顶部插入（带淡入动画）

**数据来源**：
- `store.alarmStats`（轮询）
- `store.recentAlarms`（初始化加载 + WS 增量）

**样式**：critical 级别闪烁红边框 1 秒。

#### ④ DataTrend.vue（数据趋势）

**布局**：
- 顶部 4 个小标签页切换：温度 / 湿度 / 人感 / 烟雾
- 主区域：ECharts 折线图
- 默认显示"温度"，可在多个指标间切换

**ECharts 配置要点**：
```javascript
{
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 30, top: 30, bottom: 40 },
    xAxis: { type: 'time', axisLabel: { color: '#888' } },
    yAxis: { type: 'value', axisLabel: { color: '#888' }, splitLine: { lineStyle: { color: '#333' } } },
    series: [{
        type: 'line',
        smooth: true,
        showSymbol: false,
        areaStyle: { color: 'rgba(64, 158, 255, 0.3)' },
        lineStyle: { color: '#409eff', width: 2 },
        data: history.map(p => [p.recorded_at, parseFloat(p.value)])
    }]
}
```

**实时更新**：监听 WS `history_tick` 事件，追加最新点。

#### ⑤ SceneRules.vue（场景联动）

**布局**：
- 2×2 网格，4 张规则卡片
- 每张卡片：规则名 + 触发条件 + 当前状态灯（绿=启用 / 灰=禁用）
- 底部显示触发次数

**数据来源**：`store.sceneRules`（5 秒轮询 + WS `rule_triggered` 增量）

**样式**：刚触发的卡片闪烁高亮 1 秒。

#### ⑥ OnlineRate.vue（设备在线率）

**布局**：单个 ECharts 饼图，居中显示百分比。

**ECharts 配置**：
```javascript
{
    series: [{
        type: 'pie',
        radius: ['70%', '90%'],
        avoidLabelOverlap: false,
        label: { show: false },
        data: [
            { value: online, name: '在线', itemStyle: { color: '#67c23a' } },
            { value: offline, name: '离线', itemStyle: { color: '#f56c6c' } }
        ]
    }],
    graphic: [{
        type: 'text',
        left: 'center', top: 'center',
        style: { text: `${online_rate}%`, fontSize: 32, fill: '#fff' }
    }]
}
```

---

## 7. WebSocket 协议规范

### 7.1 连接
```
ws://localhost:8083/ws/dashboard
```

### 7.2 消息格式
所有消息为 JSON：
```json
{
    "type": "事件类型",
    "data": { ... },
    "ts": 1725936000.123
}
```

### 7.3 事件清单

| type | data 字段 | 触发时机 |
|------|-----------|---------|
| `device_status` | `{key: value, ...}` 全量 | Bridge 上行解析后 |
| `alarm_new` | `{id, level, message, rule_name, triggered_at}` | 告警写入数据库后 |
| `rule_triggered` | `{id, name, action_type, trigger_count}` | 场景规则命中后 |
| `relay_changed` | `{key, value}` | 大屏控制下发后 |
| `history_tick` | `{temperature: [...], humidity: [...], ...}` | 每 5 秒推送折线图最新点 |

### 7.4 推送策略
- `device_status`：每次 device_status 表任意 key 变化时推
- `history_tick`：每 5 秒推一次（批量）
- `alarm_new` / `rule_triggered`：实时
- `relay_changed`：实时

---

## 8. 启动脚本（start_all.bat）

**Windows 批处理**：
```batch
@echo off
chcp 65001 >nul
cd /d %~dp0

echo ========================================
echo   Day10.2 智慧物联网大屏
echo ========================================

REM 1. 启动后端（内含 Bridge）
echo [1/3] 启动后端 (port 8083)...
start "Day10.2-Backend" cmd /k "cd backend && python app.py"

REM 2. 启动前端 dev server
echo [2/3] 启动前端 dev server (port 5173)...
start "Day10.2-Frontend" cmd /k "cd frontend && npm run dev"

REM 3. 等待并打开浏览器
echo [3/3] 等待 8 秒后打开浏览器...
timeout /t 8 /nobreak >nul
start http://localhost:5173

echo ========================================
echo   大屏已启动!
echo   - 大屏地址: http://localhost:5173
echo   - 后端 API: http://localhost:8083/api
echo   - WebSocket: ws://localhost:8083/ws/dashboard
echo ========================================
pause
```

---

## 9. 验收标准（可测试清单）

### 9.1 启动验收
- [ ] 执行 `start_all.bat` 后浏览器自动打开 `http://localhost:5173`
- [ ] 大屏正常渲染 6 个模块，深色科技风
- [ ] 后端日志无报错，端口 8083 正常监听
- [ ] 前端无控制台错误

### 9.2 全链路验收
- [ ] 真实 Bridge 模式：Bridge 连上 `172.16.4.211:9783`，接收 ESP32 上行数据
- [ ] 大屏"数据趋势"模块能看到温度/湿度等指标实时变化
- [ ] Bridge 故障后 5 秒内自动重启
- [ ] Bridge 不可达时 fallback 到 `fake_bridge.py` 产生模拟数据

### 9.3 下行链路验收
- [ ] 在大屏点击 `ChannelStatus` 模块的继电器按钮 → 后端 `/api/devices/toggle` 返回 200
- [ ] MQTT 实际下发（log 中能看到 publish）
- [ ] 设备状态变化后通过 WS 推回大屏，按钮状态更新

### 9.4 实时刷新验收
- [ ] WebSocket 连接成功，DevTools Network 中 `WS` 状态显示绿色
- [ ] 断网后 30 秒内自动重连成功
- [ ] 告警产生后大屏"告警信息"列表立即出现新告警（不轮询）
- [ ] 场景规则触发后大屏"场景联动"卡片触发次数 +1

### 9.5 数据准确性验收
- [ ] `/api/overview` 返回的 total/online/offline 与数据库一致
- [ ] 设备在线率计算正确（(online/total)*100，保留 1 位小数）
- [ ] 历史数据保留 60 分钟，超时自动清理
- [ ] 继电器状态显示与 `device_status` 表完全一致

### 9.6 性能与稳定性验收
- [ ] 持续运行 30 分钟无内存泄漏
- [ ] WebSocket 长时间无消息不自动断开（心跳或 server 端 keep-alive）
- [ ] 大屏页面 5 秒内首屏渲染完成

---

## 10. 不在本期范围（明确排除）

- ❌ 项目文档（README、物模型、协议包、接口文档、部署手册、总结报告）
- ❌ 性能测试报告
- ❌ 移动端 App
- ❌ 单元测试 / pytest（本期仅做端到端手动验收）
- ❌ Docker 化部署
- ❌ 用户权限系统（Day10 已实现但本期大屏不接入登录）

---

## 11. 风险与备注

### 11.1 已识别风险
- **网络限制**：`172.16.4.211:9783` 可能在内网，Trae Code 开发机如不在同一网段需用 `fake_bridge.py`
- **Node 环境**：开发机需要装 Node v18+，Trae Code 通常自带
- **端口冲突**：如 8083 或 5173 被占用，需修改 `app.py` 和 `vite.config.js`

### 11.2 与 Day10 的差异
- 数据库路径：`simulator/day10_2/iot_platform.db`（独立）
- 端口：8083（不是 8081）
- 前端工程：独立 Vite 项目，不是 Flask 渲染模板
- 用户系统：本期大屏直接通过浏览器访问，无登录

### 11.3 调试技巧
- WebSocket 调试：浏览器 DevTools → Network → WS
- ECharts 调试：`option` 加 `console.log(option)` 查看是否生效
- 端口冲突：`netstat -ano | findstr :8083`

---

## 12. 完成后输出

开发完成后，请输出：
1. 完整的目录树（`tree /F` 或 `find .`）
2. 各文件的关键代码片段（db.py 新增表、ws_hub.py、6 个 Vue 组件的 props/emits）
3. 启动日志（确认无报错）
4. 验收清单的实际测试结果