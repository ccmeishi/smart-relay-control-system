# Day10.2 · 智慧物联网实时监控大屏（Vue3 + ECharts + WebSocket）

> Day10 做好了「场景联动 + 告警」，但管理后台是给管理员用的**表格网页**。
> Day10.2 把这些数据做成一块**深色科技风、会自己跳动、能点按钮控设备**的**实时监控大屏**——挂在显示器/投影上给老师演示用。
> 对应欧阳群刚老师「Day10 大屏 + 全链路联调 + 项目总结」中的**大屏可视化 + 全链路联调**部分。

## 一、这一天要做什么（先看懂）

做一块大屏，满足四件事：

1. **数据是真的、会自己动**：温度/湿度/人感/烟雾折线实时滚动，继电器状态实时翻转——不是写死的假图；
2. **能反向控制**：在大屏上点继电器按钮，命令真的通过 MQTT 下发到 ESP32（验证「下行」链路）；
3. **实时推送**：新告警、规则触发、状态变化靠 WebSocket **立刻**弹出来，不用刷新页面（验证「上行」链路）；
4. **没有硬件也能演**：连不上实验室 MQTT / 没有 ESP32 时，自动切换到内置**模拟数据源**，大屏永远有数据、永不空白。

> 💡 **新手最该知道的一点**：Day10.2 **不需要 ESP32、不需要连实验室 MQTT**，在自己电脑上**双击 start_all.bat 就能看到完整效果**（自动用模拟数据）。有真实板子时它又会自动切成真实数据。

## 二、技术栈（了解即可，不用自己装一堆）

| 层 | 用的什么 | 说明 |
|----|----------|------|
| 前端 | Vue 3 + Vite + Pinia + ECharts 5（纯 CSS，没用 UI 框架） | 大屏页面 |
| 实时通信 | 浏览器原生 WebSocket + 后端 flask-sock | 自动重连（指数退避） |
| 后端 | Python Flask 3，端口 **8083** | 提供网页 + 接口 + WebSocket |
| 数据库 | SQLite（`day10_2/iot_platform.db`，WAL 模式） | Bridge 进程和 Flask 进程共用 |
| 数据源 | 真实 `gateway_bridge.py` 或模拟 `fake_bridge.py` | 自动二选一 |

> 仓库里已带**构建好的前端**（`frontend/dist/`），所以**大多数情况下你不用装 Node.js**，Python 就能把大屏跑起来。只有要改前端代码时才需要 Node 18+。

## 三、全链路架构（数据怎么流的）

```
【上行：设备 → 大屏】
 ESP32 网关 ──MQTT──► Bridge(bridge/gateway_bridge.py)
   或模拟源 fake_bridge.py（无硬件时）
                            │ 写 SQLite
                            ▼
              device_status(最新值) / device_status_history(历史) / alarm_records(告警)
                            │
              Flask 后台轮询线程 DataWatcher 每 0.5 秒扫一次
                            │ 发现变化 → 写历史 → WebSocket 广播
                            ▼
                   ws://localhost:8083/ws/dashboard
                            ▼
                     大屏 Vue 页面实时刷新

【下行：大屏 → 设备】
 大屏点继电器按钮 ──POST /api/devices/toggle──► Flask
              └──MQTT properties/write──► ESP32 继电器动作
              └──同时更新库 → WS relay_changed ──► 大屏按钮即时翻转
```

**为什么中间非要用 SQLite 中转？** Bridge 是一个独立进程，Flask 是另一个进程，它俩不能直接互相调用。统一通过数据库解耦：Bridge 只管往库里写，Flask 的后台线程负责盯着库、有变化就广播给网页。

## 四、代码结构（每个文件是干什么的）

```
day10_2/
├── start_all.bat            ⭐ 双击它！自动装依赖/检测端口/首次自动构建/启动/开浏览器
├── requirements.txt         Python 依赖(flask, flask-sock, paho-mqtt)
│
├── backend/                 ← Flask 后端（电脑上跑，端口 8083）
│   ├── app.py               ⭐ 入口：托管网页 + WebSocket 端点 + 后台轮询广播线程
│   ├── api.py               ⭐ REST 接口 + 点继电器时往 MQTT 下发命令
│   ├── db.py                ⭐ SQLite 数据层(8 张表) + 场景规则引擎 + 在线率统计
│   ├── ws_hub.py            WebSocket 连接池管理 + 向所有网页广播
│   ├── bridge_runner.py     数据源「管家」：选真实/模拟源，崩溃 5 秒自动重启
│   └── log_setup.py         统一日志：同时打印到控制台并写 logs/day102.log
│
├── bridge/
│   └── gateway_bridge.py    真实 Bridge（从 day10 复制，只改了数据库路径；client_id 独立）
│
├── simulator/               ← 无硬件时用的模拟程序
│   ├── fake_bridge.py       ⭐ 模拟数据源：自己造温/湿/人/烟/继电器 + 断网 + 异常冲高
│   └── modbus_slave_sim.py  Modbus 从站模拟器（接真板子时用）
│
├── esp32_firmware/          ESP32 固件 + config.json（MQTT 地址/账号唯一可信来源）
│
├── frontend/                Vue3 前端工程
│   ├── dist/                ⭐ 已构建好的网页，Flask 直接拿来用（免装 Node）
│   └── src/
│       ├── App.vue             大屏整体 3 列布局 + 键盘快捷键
│       ├── style.css           全局深色科技风样式（含滚动适配、扫描线动画）
│       ├── main.js             Vue 入口
│       ├── api/http.js         axios 封装（调 REST 接口）
│       ├── api/ws.js           WebSocket 客户端（断线指数退避自动重连）
│       ├── stores/dashboard.js Pinia 状态仓库：收 WS 事件、存全部大屏数据
│       └── components/         6 个大屏模块（见下表）
│
├── logs/                    运行日志（自动生成，已被 git 忽略）
└── iot_platform.db          SQLite 数据库（首次运行自动生成）
```

### 6 个大屏模块（frontend/src/components/）

| 文件 | 模块 | 显示什么 / 能做什么 |
|------|------|--------------------|
| **DeviceOverview.vue** | 设备概览 | 设备总数、在线数、离线数、在线率进度条 |
| **ChannelStatus.vue** | 通道状态·继电器控制 | 4 路继电器卡片，**点一下就下发 MQTT 控制**，下发中转圈、500ms 防抖 |
| **AlarmPanel.vue** | 告警信息 | 今日/未处理/已处理 3 个计数、级别环形图、滚动告警列表，可全部确认/清除 |
| **DataTrend.vue** | 数据趋势·实时采集 | 温度/湿度/人感/烟雾 标签切换，ECharts 面积折线，5 秒滚一个新点 |
| **SceneRules.vue** | 场景联动 | 全部规则卡片（条件/级别/触发次数），触发时高亮，按触发次数排序 |
| **OnlineRate.vue** | 设备在线率 | ECharts 环形图，中间大百分比 + 在线 x/总数 |

## 五、数据库（8 张表）

复用 day10 的 6 张：`device_mappings`、`users`、`login_sessions`、`device_status`、`scene_rules`、`alarm_records`。

Day10.2 **新增/改动**：

| 表 / 列 | 作用 |
|---------|------|
| `device_status_history`（新表） | 设备状态时序数据，喂「数据趋势」折线图。每个 key 每 30 秒存一点，默认只留最近 60 分钟，超了自动清理 |
| `dashboard_config`（新表） | 大屏参数（历史保留时长、广播间隔、轮询间隔） |
| `scene_rules.last_observed_value` / `last_observed_count`（新增两列） | 把「传感器稳定计数」从内存挪进数据库，重启不丢，首次上报不会被误跳过。老库首次启动会自动 `ALTER TABLE` 加列 |

## 六、运行步骤（从零开始，照着做）

### 方式一：一键启动（99% 的人选这个）

直接**双击 `start_all.bat`**。脚本会自动：

1. 检查有没有 Python；
2. 检查 flask / flask-sock / paho-mqtt，**缺了自动 pip 安装**；
3. 检查 8083 端口是否被占用（被占会问你要不要继续）；
4. 第一次运行如果 `frontend/dist` 不存在，自动 `npm install + npm run build`（需要 Node 18+；仓库已带 dist，通常跳过）；
5. 启动后端（它内部会再拉起数据源进程）；
6. 等 8 秒自动打开浏览器。

然后浏览器访问 **http://localhost:8083**，大屏就出来了（**无需登录**）。

正常时后端黑窗口会打印类似：
```
[runner] MQTT broker 不可达 → 回退到 FakeBridge (模拟数据)
[watcher] 数据轮询线程已启动
2026-09-10 ... [INFO] [fake] FakeBridge 启动, 每 2.0s 上报一批模拟数据
```

### 方式二：前端开发模式（只有要改 Vue 代码时才用，热更新）

```powershell
# 窗口 1：后端
cd backend
python app.py

# 窗口 2：前端开发服务器（端口 5173，自动把 /api、/ws 代理到 8083）
cd frontend
npm install
npm run dev
# 浏览器开 http://localhost:5173
```

> 改完 `frontend/src` 想让一键启动（8083）也生效，记得 `cd frontend && npm run build` 重新打包。

### 强制模拟 / 强制真实数据源

后端选数据源有三种情况（逻辑在 `bridge_runner.py`）：

| 优先级 | 条件 | 用哪个源 |
|--------|------|---------|
| 1 | 环境变量 `DAY102_FORCE_FAKE=1` | **强制模拟**（现场演示、没网时用） |
| 2 | 能连通 MQTT `172.16.4.211:9783` | 真实 Bridge（ESP32 数据） |
| 3 | 连不上 MQTT | **自动回退** FakeBridge 模拟数据 |

```powershell
# 强制模拟（Windows cmd）
set DAY102_FORCE_FAKE=1
cd backend && python app.py
```

数据源进程一旦崩溃，管家会在 5 秒内自动重启。

## 七、大屏上的数字分别怎么来的（重点讲两个）

### 7.1 设备在线率是按什么判断的？

**按「最近 60 秒有没有上报数据」判断**（`db.py` 的 `get_overview`）：

```
设备总数 8 = device_mappings 里启用的映射条数（4 继电器 + 温/湿/人/烟 4 传感器）
在线数    = device_status 里 updated_at 在最近 60 秒内被刷新过的条数
离线数    = 总数 − 在线数
在线率    = 在线 ÷ 总数 × 100%
```

数据源每 **2 秒**写一次最新值并刷新时间；Flask 每 0.5 秒统计一次。所以：
- 某通道正常上报 → 时间一直是几秒内 → **在线**；
- 某通道连续 **超过 60 秒**没上报 → **离线**（在线率从 8/8=100% 掉到 7/8=87.5%）；
- 恢复上报后自动回到在线。

模拟源会**每约 80 秒随机让一个传感器「断网 75 秒」**（>60 秒阈值），大屏上就能看到某个通道偶尔离线、随后自愈的效果。**如果把后端整个关掉超过 60 秒，8 个通道会全部显示离线**——这是对的，重新启动即可恢复。

### 7.2 「今日告警很多，但某条规则触发次数是 0」是 bug 吗？

**不是 bug**，两个数字来源不同：

| 数字 | 存在哪 | 含义 |
|------|--------|------|
| 今日告警 / 已处理 | `alarm_records` 表 | 历史累积的告警**事件条数**（一次触发一条） |
| 规则卡片上的「触发 N 次」 | `scene_rules.trigger_count` | 这条规则**累计命中并执行动作的次数**（存数据库，重启不清零） |

预置 4 条规则里：
- 「有人自动开灯 / 无人自动关灯」：人感每几秒翻转，触发非常频繁（一两百次很正常）；
- 「高温自动断电(>35) / 烟雾告警联动(>50)」：正常温度只有 24~31、烟雾 3~20，**正常情况下根本到不了阈值**，所以它俩长期是 0——这是**正确的**。

为了能演示这两条严重规则，模拟源专门做了**异常冲高**（见下节）。另外场景联动面板已改为**显示全部规则并按触发次数排序**，不会再只看到两条 0 次的。

### 7.3 模拟数据的三种「戏」（fake_bridge.py 自动演）

- **日常飘动**：温度在 24~31、湿度 45~68、烟雾 3~20 间平滑随机游走，人感偶尔 0/1 翻转，每 **2 秒**一批；
- **异常冲高**：每约 120 秒有 60% 概率，让温度冲到 **37（>35）** 或烟雾冲到 **62（>50）**，持续约 20 秒后自然回落。这期间你能在大屏看到：红色严重告警弹出 + 继电器被自动断电 + 规则触发次数 +1；
- **随机断网**：每约 80 秒让一个传感器停报 75 秒，在线率短暂掉到 87.5% 后自愈。

## 八、键盘快捷键 & 显示适配

- **F**：全屏；**Esc**：退出全屏；**R**：手动重连 WebSocket（焦点在输入框时不触发）。
- 右上角绿色「实时连接」表示 WebSocket 正常；变灰/红色表示断开，会自动按 1/2/4/8 秒退避重连，不用手动刷新。
- 页面支持**纵向滚动**：浏览器缩放比例大或窗口矮时，每个区域至少 360px 高，整页可上下滚动，不会再出现内容被切掉、看不全的问题。

## 九、REST 接口与 WebSocket 事件（给想深入的人）

REST 前缀 `/api`：

| 方法 | 路径 | 作用 |
|------|------|------|
| GET | `/overview` | 总数/在线/离线/在线率 |
| GET | `/device-status` | 8 个通道当前值 |
| GET | `/alarm-stats` | 告警三态 + 级别 + 今日数 |
| GET | `/alarms/recent?limit=10` | 最近告警 |
| GET | `/scene-rules` | 规则列表（含触发次数） |
| GET | `/history/<key>?minutes=30` | 某通道历史折线 |
| POST | `/devices/toggle` | 控继电器 `{key:"relay1",value:"1"}` → MQTT 下发 |
| POST | `/alarms/<id>/ack`、`/alarms/ack-all`、`/alarms/clear-all` | 单条确认 / 全部确认 / 全部清除 |

WebSocket（`ws://localhost:8083/ws/dashboard`）事件：`device_status`、`alarm_new`、`rule_triggered`、`relay_changed`、`history_tick`、`overview_tick`。

## 十、Day10 vs Day10.2 对比

| 项 | Day10 | Day10.2 |
|----|-------|---------|
| 界面 | Flask 服务端渲染的表格后台 | **Vue3 + ECharts 实时大屏**（无登录，直接展示） |
| 实时方式 | 前端每 30 秒轮询 | **WebSocket 实时推送**（+ 轮询兜底） |
| 硬件依赖 | 需要真实 ESP32 + 实验室 MQTT | **无硬件自动模拟**，有硬件自动切真实 |
| 数据库 | day10/iot_platform.db | day10_2/iot_platform.db（独立，互不污染） |
| 端口 | 8081（需要登录） | **8083（大屏免登录）** |
| 新增表 | scene_rules、alarm_records | 再加 device_status_history、dashboard_config |
| 折线图 / 环形图 | 无 | ECharts 实时折线 + 在线率/告警环形图 |

## 十一、故障排查（这一阶段踩过的坑都在这）

| 现象 | 原因 | 解决 / 说明 |
|------|------|------------|
| 大屏打开是**空白**，F12 控制台报 MIME 错（js 被当 text/plain） | Windows 下 Flask 偶尔把 `.js` 识别成 `text/plain`，浏览器拒绝执行 ES 模块 | `app.py` 已用 `mimetypes.add_type("application/javascript",".js"/".mjs")` 修正，勿删 |
| **双击 start_all.bat 黑窗一闪而过** | ① bat 是 LF 换行（cmd 解析多行括号块会崩）；② `if(…)` 块里 echo/choice 文本含字面括号，报 `… was unexpected at this time` | 已修：文件统一 **CRLF + 纯 ASCII 英文**，且 `if` 块内不出现 `( )`，所有退出分支都加 `pause`。自己改坏就回仓库拉取 |
| bat 满屏 `'aho-mqtt'/'hon' 不是内部命令` 之类乱码 | UTF-8 中文被 cmd 按 GBK 解析，多字节中文「吞」掉后面的英文字母 | 启动脚本一律用**纯英文**，从根上避免 |
| 大屏有界面但**没数据** | 无 ESP32 且当前是真实源 / MQTT 不通 | 用 `set DAY102_FORCE_FAKE=1` 后重启 `python app.py` |
| 8083 打不开 / 端口被占 | 上一个后端没关 | `netstat -ano | findstr :8083` 找 PID 结束，或直接关旧窗口 |
| 8 个通道**全离线(0%)** | 数据源进程停了超过 60 秒 | 重启 start_all.bat；这正是「60 秒心跳判活」的正常表现 |
| 告警几百条但严重规则触发 0 次 | 温度/烟雾正常到不了 35/50 阈值 | 等模拟源的「异常冲高」（约 2 分钟一次），或接真板子用 set_modbus 造值 |
| 折线图一开始查出全量历史、点很密 | 旧 SQL 用 `recorded_at >= datetime('now',…)`，但时间存的是带 `T` 的 ISO 格式，字符串比较失效 | 已改为 `datetime(recorded_at) >= datetime('now',…)` 三处统一转换 |
| 数据库偶尔报 `database is locked` | Bridge 子进程和 Flask 并发写同一 SQLite | 已开 WAL + `busy_timeout=5000` + `synchronous=NORMAL` |
| 历史/广播刷太猛，数据库暴涨、WS 刷屏 | 每 0.5 秒变化就写历史 + 广播 | 已节流：历史每个 key **30 秒**存一点；状态广播 **1.5 秒**一次（继电器点击仍即时反馈） |
| 后端重启后规则第一次满足却不触发 | 早期「稳定计数」存内存，重启清零 | 已落库到 `last_observed_value/count`，重启不丢；老库启动自动加列 |
| 控制台信息太少 / 出错难追 | 原来全用 print | 已统一 `log_setup.py`，带时间戳和级别，写 `logs/day102.log` |
| 改了前端但页面没变 | 生产模式(8083)用的是 dist 构建产物 | `cd frontend && npm run build` 后刷新；开发热更新用 5173 |
| 页面缩放后底部被切掉、不能滚 | 旧 CSS 固定 `100vh + overflow:hidden` | 已改 `min-height:100vh + overflow-y:auto + 行 minmax(360px,1fr)` |

## 十二、验收清单

- [ ] 双击 start_all.bat，无乱码、不闪退，自动开 http://localhost:8083
- [ ] 大屏 6 个模块都渲染出来，右上角绿色「实时连接」
- [ ] 温度折线每 5 秒左右向右滚一个新点；数字在合理范围飘动
- [ ] 点某个继电器按钮：按钮转圈→状态翻转（后端日志能看到 MQTT 实际 publish）
- [ ] 等约 1~2 分钟出现一次温度/烟雾异常冲高：红色严重告警 + 继电器自动断电 + 规则触发次数 +1
- [ ] 告警列表能「全部确认」「全部清除」，三个统计卡随之变化
- [ ] 某传感器断网时在线率短暂掉到 87.5%，恢复后回 100%
- [ ] 场景联动面板能看到全部 4 条规则及各自真实触发次数
- [ ] 把浏览器窗口缩小/放大缩放比例，页面能上下滚动、内容不被裁切
- [ ] F 能全屏、Esc 退出、R 能重连
- [ ] 日志文件 `logs/day102.log` 有带时间戳和级别的记录

## 十三、Day10.2 学了什么

- **前后端分离 + WebSocket 实时推送**：和「定时刷新网页」的体验差别；指数退避自动重连；
- **进程解耦**：两个独立进程通过 SQLite 通信，而不是硬绑在一起；
- **实时系统的节流思想**：变化就存/就推会把库和网络打爆，要按时间窗口节流，同时保留关键动作（点击继电器）的即时性；
- **SQLite 多进程**：WAL、busy_timeout、时间格式比较（ISO `T` 要用 `datetime()` 转换）这些实战坑；
- **降级容错**：真实数据源不可用时自动回退模拟，保证演示永不空白；
- **大屏自适应**：用 grid `minmax + min-height + overflow` 兼顾「铺满」和「小屏可滚」。

---

## 附录：常见手动命令速查

```powershell
cd simulator\day10_2

# 一键启动（推荐）
start_all.bat

# 仅启动后端（已在 backend 目录）
python app.py

# 强制模拟
set DAY102_FORCE_FAKE=1
python backend\app.py

# 重新构建前端（改了 Vue 代码后）
cd frontend
npm run build

# 查 8083 占用
netstat -ano | findstr :8083

# 看后端日志
type logs\day102.log
```
