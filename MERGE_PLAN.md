# MERGE_PLAN.md — day1~day10.2 整合为单项目方向方案

> 给 Trae Code 落实的整合方向  
> 整合产物存放：`E:\shixiproject\traeproject1\最终版\`（**新建子目录**，与 day1~day10_2 并列）  
> 原 day1~day10_2 文件夹：**完整保留**于 `E:\shixiproject\traeproject1\simulator\`，方便他人查阅演进过程

---

## 一、整合目标

把 day1 ~ day10.2 共 8 个独立 day 的产出，整合为一个**对外可展示的完整项目**「智能继电器控制系统」：

```
最终交付物（全部在 最终版/ 子目录下）:
  最终版/
    ├── README.md              ← 入口（项目简介 + 快速开始 + 架构图）
    ├── docs/                  ← 分章节详细文档
    ├── start_all.bat          ← 一键启动（实物/模拟器双模式）
    ├── backend/               ← 统一后端
    ├── frontend/              ← 统一前端（Vue3 SPA）
    ├── firmware/              ← ESP32-C3 固件（最新版）
    ├── tests/                 ← pytest 单测 + e2e 脚本
    ├── tools/                 ← 工具脚本
    ├── pytest.ini
    ├── requirements.txt
    └── .gitignore

原项目目录（保持不动，仅作历史参考）:
  simulator/
    ├── day1/    day2/    day5/    day7/    day8/    day9/    day10/    day10_2/
    ├── esp32/   tools/   tests/
    ├── README.md
    └── pytest.ini
```

---

## 二、整合范围与产物去重

### 2.1 哪些 day 内容进 最终版/，哪些保留在 simulator/

| 原内容 | 状态 | 整合方案 | 备注 |
|--------|------|----------|------|
| `simulator/day1/` | 留在原位 | 不动 | 教学价值 + 演进记录 |
| `simulator/day2/` | 留在原位 | 不动 | JetLinks 协议说明保留 |
| `simulator/day5/` | 提取最新版固件 | → `最终版/firmware/` | ESP32 固件取 day5+day7+day8 合并最新版 |
| `simulator/day7/` | 留在原位 | 不动 | 演进记录 |
| `simulator/day8/` | **核心来源** | gateway_bridge.py 取最新版进 `最终版/backend/` | 网关+Bridge 主架构 |
| `simulator/day9/` | **核心来源** | web 后台 + 权限系统进 `最终版/backend/` + `最终版/frontend/views/` | 用户/会话/路由 |
| `simulator/day10/` | **核心来源** | 场景联动 + 告警进 `最终版/backend/` | 规则引擎 |
| `simulator/day10_2/` | **核心来源** | Vue3 大屏 + WS + 30s 节流 + WAL 进 `最终版/frontend/` + `最终版/backend/` | 最新最全架构 |
| `simulator/esp32/` | 整合取最新版 | → `最终版/firmware/`（取 day8 main.py 最新版） | 其余 day 固件不动 |
| `simulator/tools/` | 整合去重 | → `最终版/tools/`（去重保留最新版） | modbus_sim / detect_com 等 |
| `simulator/tests/` | 整合保留 | → `最终版/tests/`（保留全部，新增 e2e） | 158 通过 + 加 e2e |

### 2.2 关键去重点（容易出问题）

1. **3 套数据库**：day9/db.py、day10/db.py、day10_2/backend/db.py — 三套 schema 已经各自独立，但表名/字段高度重叠。整合时**保留 day10_2 的最新版**（最新最全），迁移 day9/day10 的特有表/字段过来。

2. **2 套 Web 后台**：day9 用 Flask + Jinja2 + 原生 HTML（传统模板），day10_2 用 Flask + Vue3 SPA（前后端分离）。整合时**统一为前后端分离**（day10_2 的架构），把 day9 的「用户/会话/设备/路由」页面作为 Vue 路由加进来。

3. **3 个 modbus_slave_sim**：day9、day10 各一个（基本一样）。整合到 `最终版/tools/modbus_sim.py`。

4. **2 套 gateway_bridge.py**：day9、day10 各一个（day10 多场景评估）。整合到 `最终版/backend/bridge/gateway_bridge.py`，保留最新版。

5. **esp32 三版固件**：day5（继电器）、day7（Modbus 采集）、day8（网关+Bridge）。**只保留最新版（day8 main.py）**进 `最终版/firmware/`，其余保留在 `simulator/day5/day7/` 不动。

---

## 三、新目录结构（全部在 `最终版/` 子目录下）

```
traeproject1/
├── README.md                       ← 原根 README 不动
├── MERGE_PLAN.md                   ← 本文档（已存在）
├── 最终版/                         ← 【新建】整合项目根目录
│   ├── README.md                   ← 项目入口（新建）
│   ├── docs/                       ← 详细文档（新建）
│   │   ├── 00-overview.md
│   │   ├── 01-quickstart.md
│   │   ├── 02-architecture.md
│   │   ├── 03-evolution.md
│   │   ├── 04-api.md
│   │   ├── 05-deploy.md
│   │   └── 06-faq.md
│   │
│   ├── backend/                    ← 统一后端（新建）
│   │   ├── app.py                  ← Flask 入口（day10_2 版）
│   │   ├── api.py                  ← REST 路由（合并 day9 + day10 + day10_2）
│   │   ├── ws_hub.py               ← WebSocket Hub（day10_2）
│   │   ├── db.py                   ← 数据库（day10_2 版 + 增量迁移 day9 表）
│   │   ├── log_setup.py            ← 日志（day10_2）
│   │   ├── auth.py                 ← 权限/会话（day9）
│   │   ├── scene_rules.py          ← 场景联动（day10）
│   │   ├── alarm.py                ← 告警（day10）
│   │   ├── bridge/                 ← Bridge 子模块
│   │   │   ├── __init__.py
│   │   │   ├── gateway_bridge.py   ← MQTT 网关（day10 版）
│   │   │   └── fake_bridge.py      ← 模拟器（day10_2）
│   │   ├── static/                 ← 前端构建产物（Vite 输出）
│   │   ├── templates/
│   │   │   └── index.html          ← SPA 入口
│   │   ├── logs/                   ← 运行日志
│   │   ├── iot_platform.db         ← SQLite（运行时）
│   │   └── requirements.txt
│   │
│   ├── frontend/                   ← 统一前端（新建，从 day10_2 升级）
│   │   ├── package.json
│   │   ├── vite.config.js
│   │   ├── index.html
│   │   ├── src/
│   │   │   ├── main.js
│   │   │   ├── App.vue
│   │   │   ├── router/index.js     ← 新增：路由
│   │   │   ├── views/              ← 新增：各页面
│   │   │   │   ├── DashboardView.vue
│   │   │   │   ├── DevicesView.vue
│   │   │   │   ├── MappingsView.vue
│   │   │   │   ├── UsersView.vue
│   │   │   │   ├── SessionsView.vue
│   │   │   │   ├── ScenesView.vue
│   │   │   │   └── LoginView.vue
│   │   │   ├── components/         ← 组件
│   │   │   │   ├── DeviceOverview.vue
│   │   │   │   ├── ChannelStatus.vue
│   │   │   │   ├── DataTrend.vue
│   │   │   │   ├── AlarmPanel.vue
│   │   │   │   ├── SceneRules.vue
│   │   │   │   └── Layout.vue      ← 新增：含导航栏
│   │   │   ├── stores/dashboard.js
│   │   │   ├── api/http.js
│   │   │   └── style.css
│   │   └── dist/                   ← 构建产物
│   │
│   ├── firmware/                   ← ESP32 固件（取 day8 最新版）
│   │   ├── boot.py
│   │   ├── main.py                 ← 最新版（day8 main.py）
│   │   ├── config.py
│   │   ├── relay_hw.py
│   │   ├── modbus_gw.py
│   │   ├── config.json
│   │   └── tools/
│   │       └── upload.bat
│   │
│   ├── tools/                      ← 工具（合并去重）
│   │   ├── sensor_sim.py           ← day1 传感器模拟器
│   │   ├── relay_sim.py            ← day2 继电器模拟器
│   │   ├── modbus_sim.py           ← Modbus 从站（合并 day9/day10）
│   │   ├── detect_com.py           ← COM 口检测
│   │   ├── set_modbus.py           ← 写 Modbus 寄存器
│   │   └── com_tool.py             ← 串口工具
│   │
│   ├── tests/                      ← 测试（保留 + 新增 e2e）
│   │   ├── conftest.py
│   │   ├── test_esp32_modbus_gw.py
│   │   ├── test_gateway_bridge.py
│   │   ├── test_modbus_slave_sim.py
│   │   ├── test_mqtt_integration.py
│   │   ├── test_protocol_consistency.py
│   │   ├── test_sensor_simulator.py
│   │   └── e2e/                    ← 新增
│   │       ├── README.md
│   │       ├── test_e2e_full_chain.py
│   │       └── screenshots/
│   │
│   ├── start_all.bat               ← 一键启动（重写）
│   ├── stop_all.bat                ← 一键停止（新增）
│   ├── pytest.ini
│   ├── requirements.txt
│   └── .gitignore
│
└── simulator/                      ← 原 day1~day10_2，**完整保留不动**
    ├── day1/    day2/    day5/    day7/    day8/    day9/    day10/    day10_2/
    ├── esp32/   tools/   tests/
    ├── README.md
    └── pytest.ini
```

---

## 四、start_all.bat 一键启动

### 4.1 启动逻辑

```bat
@echo off
chcp 65001 > nul
title 智能继电器控制系统 - 启动器

:MENU
cls
echo === 智能继电器控制系统 ===
echo.
echo [1] 启动 - 模拟器模式（推荐演示）
echo [2] 启动 - 实物模式（需 ESP32 + 传感器）
echo [3] 启动 - 开发模式（含 npm run dev 热重载）
echo [4] 仅启动后端（不开前端）
echo [5] 跑测试（pytest + e2e）
echo [6] 清理数据库（危险）
echo [7] 退出
echo.
set /p choice=选择:

if "%choice%"=="1" start_simulator_mode
if "%choice%"=="2" start_hardware_mode
if "%choice%"=="3" start_dev_mode
if "%choice%"=="4" start_backend_only
if "%choice%"=="5" run_tests
if "%choice%"=="6" clean_db
if "%choice%"=="7" exit
goto MENU
```

### 4.2 启动流程（模拟器模式）

1. 检查 Python 3.12 + Node 18+ 环境
2. 检查 8083 端口未占用
3. 检查后端依赖 `pip install -r backend/requirements.txt`
4. 检查前端依赖 `npm install` + 构建 `npm run build`（如 dist/ 缺失）
5. 启动后端：`python backend/app.py`（后台进程）
6. 启动 fake_bridge（自动）
7. 等待 3s → 探测 http://localhost:8083/api/overview 是否 200
8. 打开浏览器 http://localhost:8083/
9. 显示快捷键提示（F/Esc/R）

---

## 五、功能合并清单

### 5.1 后端 API 合并

| 原 API | 整合后位置 | 备注 |
|--------|-----------|------|
| day10_2 `/api/overview` | `最终版/backend/api.py` | 保留 |
| day10_2 `/api/alarm-stats` | `最终版/backend/api.py` | 保留 |
| day10_2 `/api/alarms/<id>/ack` | `最终版/backend/api.py` | 保留 |
| day10_2 `/api/alarms/ack-all` | `最终版/backend/api.py` | 保留 |
| day10_2 `/api/alarms/clear-all` | `最终版/backend/api.py` | 保留 |
| day10_2 `/api/devices/toggle` | `最终版/backend/api.py` | 保留（沿用 MQTT 下发） |
| day10_2 `/api/history/<key>` | `最终版/backend/api.py` | 保留 |
| day10_2 `/api/scene-rules` | `最终版/backend/api.py` | 保留 |
| day9 `/api/devices` | `最终版/backend/api.py` | 新增：设备列表 |
| day9 `/api/mappings` | `最终版/backend/api.py` | 新增：路由映射 CRUD |
| day9 `/api/users` | `最终版/backend/api.py` | 新增：用户管理 |
| day9 `/api/sessions` | `最终版/backend/api.py` | 新增：会话管理 |
| day9 `/api/config/points` | `最终版/backend/api.py` | 新增：采集点配置 |
| day9 `/login` `/logout` | `最终版/backend/api.py` | 新增：登录登出 |

### 5.2 前端页面合并

| 原页面 | 新位置 | 整合内容 |
|--------|--------|----------|
| day10_2 App.vue（实时大屏） | `最终版/frontend/views/DashboardView.vue` | 整页保留，改用 Layout.vue 包 |
| day9 dashboard.html | 拆到 `DashboardView.vue` + `DevicesView.vue` | 拆分为多个 SPA 路由 |
| day9 devices.html | `最终版/frontend/views/DevicesView.vue` | Vue 重写 |
| day9 mappings.html | `最终版/frontend/views/MappingsView.vue` | Vue 重写 |
| day9 users.html | `最终版/frontend/views/UsersView.vue` | Vue 重写 |
| day9 sessions.html | `最终版/frontend/views/SessionsView.vue` | Vue 重写 |
| day9 login.html | `最终版/frontend/views/LoginView.vue` | Vue 重写 |
| day10 scenes.html | `最终版/frontend/views/ScenesView.vue` | Vue 重写 |
| (无) | `最终版/frontend/components/Layout.vue` | 顶部导航 + 侧边栏 + 内容区 |

### 5.3 数据库 Schema 合并

以 day10_2 的 schema 为基础（最新），从 day9 增量迁移：

```sql
-- 已存在于 day10_2
device_mappings          -- 设备路由（合并 day9 的 product_id/device_id/property_name）
device_status            -- 实时状态
device_status_history    -- 历史（带 30s 节流）
scene_rules              -- 场景规则（合并 day9 的 enabled/cooldown）
alarm_records            -- 告警
dashboard_config         -- 仪表盘配置

-- 从 day9 新增
users                    -- 用户
login_sessions           -- 登录会话
```

**合并策略**：day9 有但 day10_2 没有的表，迁移 SQL 写在 `最终版/backend/db.py:init_db()` 里，运行自动补全。

---

## 六、测试方案

### 6.1 现有 pytest 单测（保留）

从 `simulator/tests/` 拷贝到 `最终版/tests/`，已有 6 个文件 / 158 通过 / 1 xfailed：
- `test_esp32_modbus_gw.py`
- `test_gateway_bridge.py`
- `test_modbus_slave_sim.py`
- `test_mqtt_integration.py`
- `test_protocol_consistency.py`
- `test_sensor_simulator.py`

**不动**，CI 继续跑。整合后这些测试应该全过（已验证）。

### 6.2 新增 e2e 端到端测试

`最终版/tests/e2e/test_e2e_full_chain.py` 内容：

```python
"""端到端全链路测试 - 模拟演示现场操作流程

启动 backend → 启动 fake_bridge →
步骤1: 验证 /api/overview 8/8 在线
步骤2: 验证大屏 WS 推送 device_status
步骤3: POST /api/devices/toggle relay1=1
步骤4: 验证 MQTT 下发 + relay_changed 事件
步骤5: 触发温度>35 模拟值 → 验证告警入库
步骤6: 触发场景规则 → 验证触发次数+1
步骤7: POST /api/alarms/clear-all → 验证 cleared
步骤8: 截图 http://localhost:8083/ 大屏页面
"""
```

每个步骤独立 try/except，失败时保留截图。约 200~300 行代码。

### 6.3 验收标准

| 项 | 标准 |
|----|------|
| `pytest 最终版/tests/` | 158 passed + 1 xfailed 全过 |
| `pytest 最终版/tests/e2e/` | 8 步全过，生成 1 张大屏截图 |
| 演示现场操作 | 单人能在合理时间内复现 e2e 流程 |
| 启动时间 | 模拟器模式在合理时间内完成 |

---

## 七、文档方案

### 7.1 docs/ 结构（7 文件，全部在 `最终版/docs/`）

| 文件 | 内容 | 来源 |
|------|------|------|
| `00-overview.md` | 项目是什么、目标、特色、技术栈、目录图 | 综合 |
| `01-quickstart.md` | 5min 启动：模拟器模式 + 实物模式 | 综合 |
| `02-architecture.md` | 最终架构图（全链路） | 来自 day10.2 DEVELOPMENT_SPEC |
| `03-evolution.md` | day1→day10.2 的演进故事（按时间线） | 从各 day README 抽取 |
| `04-api.md` | REST + WebSocket API 完整文档 | 从 day10_2 + day9 整合 |
| `05-deploy.md` | 部署到 Pi / 服务器 / Docker | 新写 |
| `06-faq.md` | 踩坑 FAQ（20~30 条） | 从各 day README 抽 |

### 7.2 `最终版/README.md` 结构

```markdown
# 智能继电器控制系统（整合版）

[1 段简介] + [架构图] + [Demo 截图] + [核心特色] + 
[快速开始 → docs/01-quickstart.md] + 
[完整文档 → docs/] + 
[历史演进 → simulator/]（指向原 day1~day10_2）
[致谢/贡献/许可]
```

### 7.3 依赖不引入新包

最终版/ 复用 day10_2 已有的依赖，**不引入**：
- ❌ mkdocs / mkdocs-material（文档用纯 Markdown）
- ❌ pytest-cov / pytest-mock（覆盖率不计）
- ❌ docker / docker-compose（演示现场不一定有 Docker）
- ❌ 任何 Python / Node 新包

最终版/ 自身只新增**配置文件**（pytest.ini / .gitignore）和**新增文件**（start_all.bat / docs/ / e2e/）。

---

## 八、实施步骤（分阶段，每阶段独立可验收）

### Phase 1: 准备（一次性，全量移动）
- 1.1 创建 `最终版/` 子目录骨架
- 1.2 备份当前 iot_platform.db（防止误操作）
- 1.3 创建 `最终版/{backend,frontend,firmware,tools,tests,docs}` 空目录

### Phase 2: 后端合并（最关键）
- 2.1 拷贝 `simulator/day10_2/backend/*` → `最终版/backend/`
- 2.2 合并 `simulator/day9/db.py` 中的 users/login_sessions 表到 `最终版/backend/db.py` 的 init_db() 迁移逻辑
- 2.3 合并 `simulator/day9/api.py` 中的 auth/users/sessions/devices/mappings 接口到 `最终版/backend/api.py`
- 2.4 把 `simulator/day9/auth.py` 移植到 `最终版/backend/auth.py`
- 2.5 拷贝 `simulator/day10/` 的场景联动核心逻辑到 `最终版/backend/scene_rules.py`
- 2.6 拷贝 `simulator/day10/` 的告警核心逻辑到 `最终版/backend/alarm.py`
- 2.7 拷贝 `simulator/day10/gateway_bridge.py` 最新版到 `最终版/backend/bridge/`
- 2.8 跑现有 pytest 验证无回归

### Phase 3: 前端合并（最大工作量）
- 3.1 拷贝 `simulator/day10_2/frontend/src/*` → `最终版/frontend/src/`
- 3.2 加 vue-router（如 day10_2 未装）
- 3.3 创建 `最终版/frontend/src/views/` 7 个页面（Day9 内容 Vue 重写）
- 3.4 创建 `最终版/frontend/src/components/Layout.vue` 含导航
- 3.5 改造 `App.vue` → `views/DashboardView.vue`
- 3.6 前端 npm run build → dist/ 替换 `最终版/backend/static/`
- 3.7 启动后端 → 浏览器逐页验证

### Phase 4: 一键启动 + e2e
- 4.1 重写 `最终版/start_all.bat`（含菜单）
- 4.2 写 `最终版/stop_all.bat`
- 4.3 写 `最终版/tests/e2e/test_e2e_full_chain.py`
- 4.4 跑 pytest 全套 + e2e → 生成截图

### Phase 5: 文档 + 收尾
- 5.1 写 `最终版/docs/` 7 个文件
- 5.2 写 `最终版/README.md`
- 5.3 拷贝 `simulator/pytest.ini` 到 `最终版/pytest.ini`
- 5.4 拷贝 `simulator/.gitignore` 到 `最终版/.gitignore`（适当调整）
- 5.5 拷贝 `simulator/requirements-dev.txt` 到 `最终版/requirements.txt`（去重）
- 5.6 git commit（按 Phase 分批提交）
- 5.7 验收：另一个人从 0 clone → 跑 `最终版/start_all.bat` → 浏览器能看大屏

### 验证节点（每 Phase 完成时跑）

| Phase | 验证动作 |
|-------|----------|
| 1 | `最终版/` 目录存在且为空骨架 |
| 2 | `pytest 最终版/tests/` 158 通过；`/api/overview` 200 |
| 3 | `npm run build` 成功；浏览器访问 7 个路由全 200 |
| 4 | `start_all.bat` 一键启动；e2e 8 步全过 + 1 张截图 |
| 5 | 7 个 docs 文件全在；根 README 200 行内；git 提交干净 |

---

## 九、风险与缓解

| 风险 | 缓解 |
|------|------|
| **数据库合并丢数据** | Phase 1.2 强制备份 iot_platform.db；新项目用干净库（不迁移历史告警） |
| **现有 pytest 回归** | Phase 2.8 必跑，无回归才进 Phase 3 |
| **前端 day9→Vue 重写量大** | 优先重写 users/sessions/mappings，devices/scenes 可以先放最简版 |
| **实物 ESP32 测试难** | 演示默认模拟器模式，实物模式只保证编译通过不实测 |
| **整合后体积膨胀** | `最终版/` 内不放 iot_platform.db 和 logs/（进 .gitignore） |

---

## 十、关键决定（已确认）

| # | 议题 | 决定 |
|---|------|------|
| 1 | 数据迁移 | **不保留历史告警**，新项目从干净库开始 |
| 2 | esp32 固件版本 | **只保留最新版（day8 main.py）** |
| 3 | 原 day1~day10_2 目录 | **保留不动**（在 simulator/ 下，方便他人查阅演进过程） |
| 4 | 是否引入新依赖 | **不引入**（复用 day10_2 已有依赖） |
| 5 | 整合产物位置 | **新建 `最终版/` 子目录**（与 simulator/ 并列） |

---

## 十一、方案落地的 Trae Code 任务清单

整合完成后，可直接拆给 Trae Code：

```
Task 1:  建 最终版/ 骨架目录（Phase 1）
Task 2:  拷贝后端代码到 最终版/backend/（Phase 2.1）
Task 3:  合并 db.py 迁移逻辑（Phase 2.2）
Task 4:  合并 api.py + 加 auth.py（Phase 2.3-2.4）
Task 5:  移植场景联动/告警到 backend/（Phase 2.5-2.6）
Task 6:  移植 gateway_bridge.py（Phase 2.7）
Task 7:  验证 pytest 无回归（Phase 2.8）
Task 8:  拷贝前端到 最终版/frontend/（Phase 3.1-3.2）
Task 9:  Vue Router + 7 个 views + Layout（Phase 3.3-3.5）
Task 10: 前端构建 + 替换 dist（Phase 3.6-3.7）
Task 11: start_all.bat / stop_all.bat（Phase 4.1-4.2）
Task 12: 写 e2e 全链路测试（Phase 4.3-4.4）
Task 13: 写 docs/ 7 个文件 + 根 README（Phase 5.1-5.2）
Task 14: 配置 + git commit（Phase 5.3-5.6）
```

每个 Task 完成后跑测试 + 截图验收。

---

**方案已根据你的反馈更新完毕。开始 Phase 1 时告诉我即可。**
