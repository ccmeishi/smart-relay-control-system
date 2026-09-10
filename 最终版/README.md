# 智能继电器控制系统（整合版）

> 基于 ESP32-C3 四路继电器开发板 + Modbus 传感器采集 + MQTT 通信 + Flask 后端 + Vue3 实时大屏的完整物联网系统。
>
> 本目录是 day1 ~ day10.2 共 8 个开发阶段的**整合产物**，所有功能合并为单一可运行项目。原各阶段代码完整保留在 `simulator/day1 ~ day10_2/`，方便查阅演进过程。

---

## 核心特色

- **一块板子变八个设备** — ESP32 网关通过 Bridge 拆分为 4 路继电器（门锁/灯1/灯2/空调）+ 温度/湿度/人感/烟雾 4 个传感器
- **实时监控大屏** — Vue3 + ECharts 深色科技风，WebSocket 推送，免登录访问
- **场景联动引擎** — 高温自动断电、烟雾告警、有人开灯、无人关灯，四层防护（稳定计数 + 冷却 + 条件匹配 + 动作互斥锁）
- **告警三态管理** — active → acknowledged → cleared，支持单条/全部确认与清除
- **管理后台** — Flask Session 鉴权，设备控制台、路由映射、场景规则、用户管理、在线会话
- **模拟器模式** — 无硬件也能完整演示（FakeBridge 自动模拟数据飘动 + 异常冲高 + 随机断网）
- **一键启动** — `start_all.bat` 菜单选择模式，自动检测依赖/端口/前端构建

---

## 快速开始

### 模拟器模式（推荐，无需硬件）

```bat
:: 双击 start_all.bat，选择 [1] Simulator Mode
cd 最终版
start_all.bat
```

浏览器自动打开 `http://localhost:8083`，8 秒后大屏渲染、数据滚动。

### 实物模式（需 ESP32 + MQTT broker）

```bat
:: 选择 [2] Hardware Mode
start_all.bat
```

ESP32 需已刷入 `firmware/` 固件并完成 AP 配网（首次上电自动进入热点 `RELAY-SETUP-xxxx`，手机连 192.168.4.1 配置 WiFi + MQTT）。

### 开发模式（前端热重载）

```bat
:: 选择 [3] Dev Mode
start_all.bat
:: 前端访问 http://localhost:5173，后端 http://localhost:8083
```

> 详细步骤见 [docs/01-quickstart.md](docs/01-quickstart.md)

---

## 系统架构

```
ESP32-C3 网关 (relay-cc/relaycc)
   │ Modbus TCP 读温/湿/人/烟 (从站 192.168.20.59:5502, unit_id=7)
   │ 4 路 GPIO 继电器 (IO 3,4,5,7 高电平触发)
   ▼ MQTT 上报 (8 key 混一条)
Bridge (backend/bridge/gateway_bridge.py)
   │ ① 按路由表拆分转发 8 虚拟设备
   │ ② 评估场景规则 → 命中则 MQTT 控继电器 + 写告警
   ▼ 写 SQLite (WAL, 8 表)
Flask (backend/app.py) — DataWatcher 线程 0.5s 扫库
   │ 变化→写历史(30s节流)→WebSocket广播(1.5s节流)
   ▼
ws://localhost:8083/ws/dashboard → Vue3 大屏 (6 模块)
                                → 管理后台 (7 页面, 需登录)
```

**关键解耦**：Bridge 与 Flask 是两个独立进程，通过 SQLite 通信，互不阻塞。

> 完整架构说明见 [docs/02-architecture.md](docs/02-architecture.md)

---

## 目录结构

```
最终版/
├── README.md                ← 本文件
├── docs/                    ← 详细文档（7 篇）
├── start_all.bat            ← 一键启动（菜单：模拟器/实物/开发/测试/清理）
├── stop_all.bat             ← 一键停止
├── requirements-dev.txt     ← 测试依赖
├── pytest.ini
├── .gitignore
│
├── backend/                 ← 统一后端
│   ├── app.py               ← Flask 入口 (port 8083, WS + REST + 鉴权)
│   ├── api.py               ← 30+ REST 路由 (大屏 + 管理)
│   ├── db.py                ← SQLite 数据层 (8 表 + 规则引擎 + 在线率)
│   ├── ws_hub.py            ← WebSocket 连接池 + 广播
│   ├── bridge_runner.py     ← 数据源子进程管理 (真实/模拟自动选择)
│   ├── log_setup.py         ← 分级日志
│   └── bridge/
│       ├── gateway_bridge.py ← 真实 MQTT Bridge (ESP32 → 虚拟设备)
│       └── fake_bridge.py    ← 模拟数据源 (飘动 + 异常冲高 + 断网)
│
├── frontend/                ← Vue3 SPA
│   ├── src/
│   │   ├── App.vue          ← 根组件 (router-view)
│   │   ├── router/          ← 路由 (大屏免登录, 管理页需登录)
│   │   ├── views/           ← 8 页面 (Dashboard/Login/Devices/Mappings/Scenes/Users/Sessions/Config)
│   │   ├── components/      ← 6 大屏模块 + Layout 导航
│   │   ├── stores/          ← Pinia (dashboard + auth)
│   │   └── api/             ← HTTP + WebSocket 客户端
│   └── dist/               ← 构建产物 (已提交, 免 Node 部署)
│
├── firmware/                ← ESP32-C3 MicroPython 固件
│   ├── main.py / boot.py    ← 入口
│   ├── ap_config.py         ← AP 配网 (热点 + Web 表单)
│   ├── app_config.py        ← 配置读写
│   ├── modbus_gw.py         ← Modbus TCP 主站 (时间片轮询)
│   ├── relay_hw.py          ← GPIO 抽象 (高电平触发)
│   └── config.json          ← MQTT/WiFi 凭据 (唯一可信源)
│
├── tools/                   ← 工具脚本
│   ├── modbus_slave_sim.py  ← Modbus 从站模拟器
│   ├── set_modbus.py        ← 手动写寄存器 (真实单位)
│   └── detect_com.py        ← COM 口检测
│
└── tests/                   ← pytest 测试
    ├── conftest.py          ← 共享 fixture (modbus/mqtt/bridge)
    ├── test_*.py            ← 6 个单元测试文件
    └── e2e/
        └── test_e2e_full_chain.py ← 8 步端到端测试 (全通过)
```

---

## 访问地址

| 服务 | URL | 说明 |
|------|-----|------|
| 实时大屏 | http://localhost:8083 | 免登录，深色科技风 |
| 管理后台 | http://localhost:8083/login | admin / admin123 |
| REST API | http://localhost:8083/api/overview | JSON |
| WebSocket | ws://localhost:8083/ws/dashboard | 实时推送 |
| 前端开发 | http://localhost:5173 | npm run dev 热重载 |

**大屏快捷键**：`F` 全屏 ｜ `Esc` 退出全屏 ｜ `R` 重连 WebSocket

---

## 核心机制

| 机制 | 说明 |
|------|------|
| 数据源选择 | `DAY102_FORCE_FAKE=1` 强制模拟 → MQTT 可达用真实 Bridge → 不可达自动回退 FakeBridge |
| 在线率 | device_status 中 60s 内有更新的通道数 ÷ 8 × 100% |
| 历史节流 | 每 key 30s 存一点，留 60 分钟自动清理 |
| WS 广播 | device_status 1.5s 节流，继电器点击即时 |
| 规则防抖 | 稳定 2 次相同值 + 冷却时间 + 级别优先级 + 继电器锁 |
| 告警三态 | active (未确认) → acknowledged (已确认) → cleared (已清除) |
| 触发计数 | 持久化到 SQLite，重启不清零 |
| 异常冲高 | FakeBridge 每约 120s 触发温度 37°C 或烟雾 62，持续 20s，演示 critical 联动 |

---

## 测试

```bat
:: 运行 e2e 全链路测试（8 步，使用模拟器模式）
cd 最终版
python -m pytest tests/e2e/ -v

:: 运行全部测试（需安装测试依赖）
pip install -r requirements-dev.txt
python -m pytest tests/ -v
```

---

## 历史演进

本项目由 day1 ~ day10.2 共 8 个开发阶段整合而来：

| 阶段 | 内容 |
|------|------|
| Day1 | PC 模拟器 + Modbus 从站 |
| Day2 | JetLinks 协议对接 |
| Day5 | ESP32 固件（继电器 + 配网） |
| Day7 | Modbus 采集 + 时间片轮询 |
| Day8 | Bridge 网关（一块板子→多虚拟设备） |
| Day9 | SQLite 动态路由 + Flask 管理后台 + 权限 |
| Day10 | 场景联动 + 告警机制 |
| Day10.2 | Vue3 实时大屏 + WebSocket + 异常冲高 |

> 完整演进故事见 [docs/03-evolution.md](docs/03-evolution.md) ｜ 原始代码见 `simulator/` 目录

---

## 技术栈

| 层 | 技术 |
|----|------|
| 板子端 | ESP32-C3, MicroPython v1.29.0, umqtt.simple, Modbus TCP |
| 后端 | Python 3, Flask 3, flask-sock (WebSocket), paho-mqtt, pymodbus, SQLite (WAL) |
| 前端 | Vue 3, Vite 5, Pinia, ECharts 5, 原生 CSS |
| 协议 | Modbus TCP, MQTT (EMQX/JetLinks), WebSocket, REST |
| 平台 | JetLinks (MQTT 接入 mqtt://172.16.4.211:9783) |

---

## 完整文档

| 文档 | 内容 |
|------|------|
| [00-overview.md](docs/00-overview.md) | 项目概述 |
| [01-quickstart.md](docs/01-quickstart.md) | 快速开始 |
| [02-architecture.md](docs/02-architecture.md) | 架构设计 |
| [03-evolution.md](docs/03-evolution.md) | 演进历史 |
| [04-api.md](docs/04-api.md) | API 文档 |
| [05-deploy.md](docs/05-deploy.md) | 部署指南 |
| [06-faq.md](docs/06-faq.md) | 常见问题 |

---

## 许可

本项目为实训教学项目，供学习交流使用。
