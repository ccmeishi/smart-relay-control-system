# Day 10.2 智慧物联网平台 · 实时监控大屏

> 对应欧阳群刚老师「Day10 大屏 + 全链路联调 + 项目总结」中的**大屏可视化 + 全链路联调**部分。
> Vue3 + ECharts + WebSocket 实时大屏，完整展示「设备 → 网关 → 平台 → 大屏」全链路闭环。

---

## 一、本期目标

构建一个深色科技风实时大屏：
- **实时反映设备状态**（不写死静态数据，数据来自真实 Bridge / 模拟回退）
- **点击大屏按钮控制设备**（验证下行链路：大屏 → Flask → MQTT → ESP32）
- **WebSocket 实时推送**告警 / 状态 / 趋势（验证上行链路）
- MQTT 不可达或无实物时**自动回退到模拟数据**，大屏永不空白

---

## 二、技术栈

| 层级 | 选型 |
|------|------|
| 前端 | Vue 3 + Vite 5 + Pinia + ECharts 5 + axios（原生 CSS，无 UI 库） |
| 实时通信 | 原生 WebSocket（自动重连，指数退避）+ flask-sock |
| 后端 | Flask 3（端口 **8083**） |
| 数据库 | SQLite（`day10_2/iot_platform.db`，WAL 多进程） |
| 数据源 | 真实 `gateway_bridge.py`（复用 day10）/ `fake_bridge.py`（模拟） |

---

## 三、目录结构

```
simulator/day10_2/
├── DEVELOPMENT_SPEC.md        # 开发规格说明书
├── start_all.bat              # ⭐ 一键启动（自动检测依赖/构建/启动）
├── backend/
│   ├── app.py                 # Flask 入口 + WS 端点 + 后台轮询广播线程
│   ├── db.py                  # SQLite 数据层（复用 day10 六表 + 新增两张表）
│   ├── ws_hub.py              # WebSocket 连接池 + 广播
│   ├── api.py                 # 7 个 REST 接口 + MQTT 下发
│   └── bridge_runner.py       # 数据源子进程管理（崩溃重启 + MQTT 可达检测）
├── bridge/
│   └── gateway_bridge.py      # 真实 Bridge（从 day10 复制，仅改 db 导入路径）
├── simulator/
│   ├── modbus_slave_sim.py    # Modbus 从站模拟器
│   └── fake_bridge.py         # 模拟数据源（MQTT 不可达时回退）
├── esp32_firmware/            # ESP32 固件 + config.json（MQTT 凭据唯一可信源）
├── frontend/                  # Vue3 工程
│   ├── dist/                  # 构建产物（Flask 直接托管，免装 Node 即可运行）
│   └── src/
│       ├── App.vue            # 大屏 3×3 网格布局
│       ├── api/http.js        # axios 封装
│       ├── api/ws.js          # WebSocket 自动重连客户端
│       ├── stores/dashboard.js# Pinia 状态 + 事件分发
│       └── components/        # 6 大屏模块
│           ├── DeviceOverview.vue  # ① 设备概览
│           ├── ChannelStatus.vue   # ② 通道状态(可点击控制)
│           ├── AlarmPanel.vue      # ③ 告警信息
│           ├── DataTrend.vue       # ④ 数据趋势(ECharts 折线)
│           ├── SceneRules.vue      # ⑤ 场景联动
│           └── OnlineRate.vue      # ⑥ 在线率环形图
└── logs/                      # 运行日志（git 忽略）
```

---

## 四、数据库表

复用 day10 的六张表：`device_mappings / users / login_sessions / device_status / scene_rules / alarm_records`。

**本期新增两张表**（见 `backend/db.py`）：

| 表 | 作用 |
|----|------|
| `device_status_history` | 设备状态时序数据（大屏「数据趋势」折线图），含 `gateway_key / value / recorded_at / source`，默认保留 60 分钟自动清理 |
| `dashboard_config` | 大屏配置（历史保留时长、WS 广播间隔、轮询间隔） |

---

## 五、全链路数据流向

```
【上行】ESP32 网关 ──MQTT──► Bridge(bridge/) ──写SQLite──► device_status / alarm_records
                                                              │
                                       Flask 后台轮询线程(0.5s)│ 检测变化→写历史→广播
                                                              ▼
                                              WebSocket /ws/dashboard ──► 大屏 Vue

【下行】大屏点击继电器 ──POST /api/devices/toggle──► Flask ──MQTT properties/write──► ESP332
                                       └──► 更新 device_status ──► WS relay_changed ──► 大屏
```

**进程解耦设计**：Bridge 是独立子进程，无法直接调 Flask 的广播，统一通过 SQLite 解耦——
Flask 后台 `DataWatcher` 线程每 0.5s 扫描 `device_status` / 新增告警 / 规则触发次数，
发现变化即写历史表并通过 WebSocket 广播。

**数据源选择**（`bridge_runner.py`）：
1. 环境变量 `DAY102_FORCE_FAKE=1` → 强制模拟模式（现场无 ESP32 演示用）
2. MQTT（`172.16.4.211:9783`）可达 → 真实 Bridge
3. MQTT 不可达 → 自动回退 FakeBridge 模拟数据
数据源进程崩溃 5 秒内自动重启。

---

## 六、运行步骤

### 方式一：一键启动（推荐，老师演示用）

双击 `start_all.bat`：
- 自动检测 Python / 依赖库（缺失自动安装 flask / flask-sock / paho-mqtt）
- 检测 8083 端口冲突
- 首次运行若 `frontend/dist` 不存在，自动 `npm install + npm run build`（需 Node 18+）
- 启动后端（内含数据源进程监控），8 秒后自动打开浏览器

**大屏地址：http://localhost:8083**

> `frontend/dist` 已随仓库提交，大多数情况下**无需安装 Node**，直接跑即可。

### 方式二：前端开发模式（热更新，开发用）

```bat
:: 窗口1：后端
cd backend && python app.py

:: 窗口2：前端 dev server（5173 端口，/api 与 /ws 自动代理到 8083）
cd frontend && npm install && npm run dev
:: 浏览器打开 http://localhost:5173
```

### 强制模拟模式（无 ESP32 也能演示完整数据）

```bat
set DAY102_FORCE_FAKE=1
cd backend && python app.py
```

---

## 七、接口与事件清单

### REST 接口（前缀 `/api`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/overview` | 设备概览 + 在线率 `{total, online, offline, online_rate}` |
| GET | `/device-status` | 设备实时状态 `{relay1:"1", temperature:"25.6", ...}` |
| GET | `/alarm-stats` | 告警统计（三态 + 级别分布） |
| GET | `/alarms/recent?limit=10` | 最近告警列表 |
| GET | `/scene-rules` | 场景规则列表（含触发次数） |
| GET | `/history/<key>?minutes=30` | 某采集点历史时序 |
| POST | `/devices/toggle` | 继电器控制 `{key:"relay1", value:"1"}` → MQTT 下发 + WS 广播 |

### WebSocket 事件（`ws://localhost:8083/ws/dashboard`）

| type | 触发时机 |
|------|---------|
| `device_status` | 设备状态变化（全量） |
| `alarm_new` | 新告警产生（实时） |
| `rule_triggered` | 场景规则命中（触发次数 +1） |
| `relay_changed` | 大屏点击继电器下发后 |
| `history_tick` | 每 5 秒推送折线图最新点 |
| `overview_tick` | 每 5 秒推送概览统计 |

---

## 八、六个大屏模块

| 模块 | 数据源 | 交互 |
|------|--------|------|
| ① 设备概览 | `/api/overview` + WS | 总数/在线/离线卡片 + 在线率进度条 |
| ② 通道状态 | `/api/device-status` + WS | **点击继电器按钮即下发 MQTT 控制**，500ms 防抖 |
| ③ 告警信息 | `/api/alarms` + WS | 3 统计卡 + 级别饼图 + 滚动列表（critical 红色闪烁） |
| ④ 数据趋势 | `/api/history` + WS | 温度/湿度/人感/烟雾 标签切换，ECharts 面积折线 |
| ⑤ 场景联动 | `/api/scene-rules` + WS | 4 规则卡片，触发时高亮闪烁 |
| ⑥ 在线率 | `/api/overview` + WS | ECharts 环形图，居中百分比 |

---

## 九、验收清单

- [x] `start_all.bat` 启动后浏览器打开 http://localhost:8083
- [x] 大屏渲染 6 个模块，深色科技风
- [x] 后端 8083 端口正常监听，日志无报错
- [x] WebSocket 连接成功（右上角绿色「实时连接」），断线自动重连
- [x] MQTT 可达 → 真实 Bridge；不可达 → 自动 FakeBridge 模拟数据
- [x] 点击继电器按钮 → `/api/devices/toggle` 返回 200 + MQTT 实际 publish + 按钮状态更新
- [x] 告警产生后大屏列表实时出现（WS 推送，非轮询）
- [x] 场景规则触发后卡片触发次数 +1
- [x] 历史数据保留 60 分钟自动清理
- [x] 设备在线率 = online/total × 100（保留 1 位小数）

---

## 十、排错说明

| 现象 | 原因 / 解决 |
|------|------------|
| 大屏打开空白，控制台报 MIME 错误 | 已在 `app.py` 用 `mimetypes.add_type` 修正 `.js` 为 `application/javascript`（Windows 下 Flask 偶尔识别为 text/plain） |
| 大屏有界面但无数据 | 无 ESP32 上报且 MQTT 可达 → 用 `set DAY102_FORCE_FAKE=1` 强制模拟模式 |
| 端口 8083 被占 | `netstat -ano | findstr :8083`，关闭旧窗口或改 `app.py` 端口 |
| 5173 代理失败 | 开发模式才用 5173；生产演示直接用 8083 |
| 前端改了不生效 | 改 `frontend/src` 后需 `cd frontend && npm run build` 重新构建（生产模式） |
| 真实数据想恢复 | 去掉 `DAY102_FORCE_FAKE` 环境变量重启即可 |

---

## 十一、与 day10 的区别

| 项 | day10 | day10.2 |
|----|-------|---------|
| 前端 | Flask 服务端渲染 HTML 模板 | Vue3 + Vite 独立工程（SPA） |
| 实时性 | 轮询刷新 | WebSocket 实时推送 + 轮询兜底 |
| 数据库 | day10/iot_platform.db | day10_2/iot_platform.db（独立） |
| 端口 | 8081 | 8083 |
| 登录 | 有用户权限系统 | 大屏无登录，直接访问 |
| 新增表 | — | device_status_history / dashboard_config |
