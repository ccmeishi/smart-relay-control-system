# 00 - 项目概述

## 一、这是什么

智能继电器控制系统（整合版）是一套完整的物联网实训项目，基于 **ESP32-C3 四路继电器开发板** + **Modbus 传感器采集** + **MQTT 通信** + **Flask 后端** + **Vue3 实时大屏** 构建。

一块 ESP32 板子通过 Bridge 网关拆分为 8 个虚拟设备（4 路继电器 + 4 个传感器），实现从端侧采集、协议转换、数据落地、规则联动到前端可视化的全链路闭环。

本目录是 day1 ~ day10.2 共 8 个开发阶段的整合产物，所有功能合并为单一可运行项目。

## 二、项目目标

- **教学示范**：覆盖 IoT 全栈典型技术点（嵌入式、协议、后端、前端、鉴权、测试）
- **可演示**：无硬件也能完整跑通（FakeBridge 模拟器自动补位）
- **可生产**：SQLite WAL + 子进程隔离 + 自动重启，结构贴近真实部署
- **可扩展**：路由表、规则引擎、大屏配置均入库，无需改代码即可调整

## 三、核心功能

| 模块 | 能力 |
|------|------|
| 设备接入 | 一块板子变八个设备（门锁 / 灯1 / 灯2 / 空调 + 温 / 湿 / 人 / 烟） |
| 实时大屏 | Vue3 + ECharts 深色科技风，WebSocket 推送，免登录访问 |
| 场景联动 | 高温断电、烟雾告警、有人开灯、无人关灯，四层防护（稳定计数 / 冷却 / 条件 / 动作互斥） |
| 告警管理 | active → acknowledged → cleared 三态流转，单条 / 全部确认清除 |
| 管理后台 | Flask Session 鉴权，设备控制台、路由映射、场景规则、用户、会话、网关配置管理 |
| 模拟器 | FakeBridge 数据飘动 + 异常冲高 + 随机断网，自动演示 critical 联动 |
| 一键启动 | `start_all.bat` 菜单，自动检测依赖 / 端口 / 前端构建 |

## 四、技术栈

| 层 | 技术 |
|----|------|
| 板子端 | ESP32-C3, MicroPython v1.29.0, umqtt.simple, Modbus TCP |
| 后端 | Python 3, Flask 3, flask-sock (WebSocket), paho-mqtt, SQLite (WAL + busy_timeout) |
| 前端 | Vue 3, Vite 5, Pinia, ECharts 5, 原生 CSS |
| 协议 | Modbus TCP (从站 192.168.20.59:5502 unit_id=7), MQTT (EMQX), WebSocket, REST |
| 平台 | EMQX (mqtt://172.16.4.211:9783), JetLinks 兼容报文 |
| 测试 | pytest, pymodbus==3.6.9, amqtt (e2e broker), stdlib e2e (urllib + http.cookiejar) |

## 五、目录结构

```
最终版/
├── README.md                ← 项目总览
├── docs/                    ← 详细文档（7 篇）
│   ├── 00-overview.md       ← 本文档
│   ├── 01-quickstart.md     ← 快速开始
│   ├── 02-architecture.md  ← 架构设计
│   ├── 03-evolution.md     ← 演进故事
│   ├── 04-api.md            ← API 手册
│   ├── 05-deploy.md         ← 部署指南
│   └── 06-faq.md            ← 常见问题
├── start_all.bat            ← 一键启动（7 选项菜单）
├── stop_all.bat             ← 一键停止（taskkill /T /F + wmic 兜底）
├── requirements-dev.txt     ← 测试依赖（pymodbus==3.6.9 精确锁定）
├── pytest.ini
├── .gitignore
├── backend/                 ← 统一后端
│   ├── app.py               ← Flask 入口 (port 8083, WS + REST + 鉴权)
│   ├── api.py               ← REST 路由 (29 个 @bp 装饰器)
│   ├── db.py                ← SQLite 数据层 (8 表 + 规则引擎)
│   ├── ws_hub.py            ← WebSocket Hub (6 种事件类型)
│   ├── bridge_runner.py     ← 数据源子进程管理（MQTT 自动探测 → FakeBridge 回退）
│   ├── log_setup.py         ← 分级日志
│   ├── requirements.txt     ← flask>=3.0 / flask-sock>=0.7 / paho-mqtt>=2.0
│   └── bridge/
│       ├── gateway_bridge.py ← 真实 MQTT Bridge
│       └── fake_bridge.py    ← 模拟数据源（异常冲高 + 随机断网）
├── frontend/                ← Vue3 SPA
│   ├── src/
│   │   ├── main.js          ← 入口
│   │   ├── App.vue          ← 根组件
│   │   ├── router/index.js  ← Vue Router
│   │   ├── stores/
│   │   │   ├── auth.js      ← 登录态
│   │   │   └── dashboard.js ← 大屏状态（告警硬上限 5 条）
│   │   ├── api/
│   │   │   ├── http.js      ← axios 封装
│   │   │   └── ws.js        ← WebSocket 客户端
│   │   ├── components/
│   │   │   ├── AlarmPanel.vue     ← 告警面板（max-height:200px）
│   │   │   ├── ChannelStatus.vue  ← 通道状态
│   │   │   ├── DataTrend.vue      ← 数据趋势
│   │   │   ├── DeviceOverview.vue ← 设备概览
│   │   │   ├── Layout.vue         ← 管理后台布局
│   │   │   ├── OnlineRate.vue     ← 在线率
│   │   │   └── SceneRules.vue     ← 场景规则
│   │   ├── views/
│   │   │   ├── DashboardView.vue  ← 大屏
│   │   │   ├── DevicesView.vue    ← 设备控制台
│   │   │   ├── MappingsView.vue   ← 路由映射
│   │   │   ├── ScenesView.vue     ← 场景规则
│   │   │   ├── ConfigView.vue     ← 网关配置
│   │   │   ├── SessionsView.vue   ← 在线会话
│   │   │   ├── UsersView.vue      ← 用户管理
│   │   │   └── LoginView.vue      ← 登录页
│   │   └── style.css
│   └── dist/                ← 构建产物（已提交，免 Node 部署）
├── firmware/                ← ESP32-C3 MicroPython
│   ├── main.py / boot.py    ← 入口
│   ├── ap_config.py         ← AP 配网
│   ├── app_config.py        ← 配置读写
│   ├── config.py            ← 默认配置
│   ├── modbus_gw.py         ← Modbus TCP 主站
│   ├── relay_hw.py          ← GPIO 抽象
│   ├── config.json          ← MQTT/WiFi/Modbus 从站配置
│   ├── _firmware/ESP32_GENERIC_C3-v1.29.0.bin
│   └── umqtt/               ← umqtt.simple
├── tools/                   ← 辅助工具
│   ├── modbus_slave_sim.py  ← Modbus 从站模拟器
│   ├── set_modbus.py        ← 写 Modbus 寄存器
│   ├── detect_com.py        ← COM 口检测
│   ├── sensor_simulator.py  ← 传感器模拟器
│   └── gateway_bridge.py    ← 独立 Bridge 脚本
└── tests/
    ├── conftest.py
    ├── test_esp32_modbus_gw.py
    ├── test_gateway_bridge.py
    ├── test_modbus_slave_sim.py
    ├── test_mqtt_integration.py
    ├── test_protocol_consistency.py
    ├── test_sensor_simulator.py
    └── e2e/
        ├── conftest.py                  ← taskkill /T /F + sweep orphan bridge
        └── test_e2e_full_chain.py       ← 8 步全链路
```

## 六、访问地址速查

| 服务 | URL | 说明 |
|------|-----|------|
| 实时大屏 | http://localhost:8083 | 免登录 |
| 管理后台 | http://localhost:8083/login | admin / admin123 |
| REST API | http://localhost:8083/api/overview | JSON |
| WebSocket | ws://localhost:8083/ws/dashboard | 实时推送 |
| 前端开发 | http://localhost:5173 | npm run dev |

> 大屏快捷键：`F` 全屏 ｜ `Esc` 退出 ｜ `R` 重连 WebSocket

## 七、关键技术决策

| 决策 | 原因 |
|------|------|
| Bridge 与 Flask 解耦为子进程 | 崩溃自动重启；避免 Modbus 阻塞 Flask 事件循环 |
| SQLite WAL + busy_timeout=5000 | 支持 bridge / Flask 并发读写，减少 "database is locked" |
| 数据源自动选择 | DAY102_FORCE_FAKE=1 强制模拟 → MQTT 可达用真实 → 不可达 FakeBridge 兜底 |
| 场景规则稳定计数持久化 | 写入 scene_rules.last_observed_value/count，跨重启保留，避免首次触发被跳过 |
| 告警列表前端硬上限 5 条 | 防止 FakeBridge 快速触发告警时 DOM 无限增长；max-height:200px 配合滚动 |
| Flask Session cookie 鉴权 | 免新依赖，SPA 友好（返回 JSON 401/403 而非 302 redirect） |
| pymodbus==3.6.9 精确锁定 | 3.15.x 改了 ModbusTcpClient 构造函数签名，测试直接挂 |

相关文档：[01-快速开始](01-quickstart.md) ｜ [02-架构设计](02-architecture.md) ｜ [05-部署指南](05-deploy.md)
