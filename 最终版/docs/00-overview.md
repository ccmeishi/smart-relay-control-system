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
| 设备接入 | 一块板子变八个设备（门锁/灯1/灯2/空调 + 温/湿/人/烟） |
| 实时大屏 | Vue3 + ECharts 深色科技风，WebSocket 推送，免登录访问 |
| 场景联动 | 高温断电、烟雾告警、有人开灯、无人关灯，四层防护 |
| 告警管理 | active → acknowledged → cleared 三态流转，单条/全部确认清除 |
| 管理后台 | Flask Session 鉴权，设备控制台、路由、规则、用户、会话管理 |
| 模拟器 | FakeBridge 数据飘动 + 异常冲高 + 随机断网，演示 critical 联动 |
| 一键启动 | `start_all.bat` 菜单，自动检测依赖/端口/前端构建 |

## 四、技术栈

| 层 | 技术 |
|----|------|
| 板子端 | ESP32-C3, MicroPython v1.29.0, umqtt.simple, Modbus TCP |
| 后端 | Python 3, Flask 3, flask-sock (WebSocket), paho-mqtt, SQLite (WAL) |
| 前端 | Vue 3, Vite 5, Pinia, ECharts 5, 原生 CSS |
| 协议 | Modbus TCP, MQTT (EMQX/JetLinks), WebSocket, REST |
| 平台 | JetLinks (mqtt://172.16.4.211:9783) |
| 测试 | pytest, stdlib e2e (urllib + http.cookiejar) |

## 五、目录结构

```
最终版/
├── README.md                ← 项目总览
├── docs/                    ← 详细文档（7 篇）
├── start_all.bat            ← 一键启动（7 选项菜单）
├── stop_all.bat             ← 一键停止
├── requirements-dev.txt     ← 测试依赖
├── pytest.ini
├── iot_platform.db          ← SQLite 数据库（运行后生成）
├── backend/                 ← 统一后端
│   ├── app.py               ← Flask 入口 (port 8083, WS + REST + 鉴权)
│   ├── api.py               ← REST 路由 (大屏 + 管理)
│   ├── db.py                ← SQLite 数据层 (8 表 + 规则引擎)
│   ├── ws_hub.py            ← WebSocket 连接池 + 广播
│   ├── bridge_runner.py     ← 数据源子进程管理
│   ├── log_setup.py         ← 分级日志
│   └── bridge/
│       ├── gateway_bridge.py ← 真实 MQTT Bridge
│       └── fake_bridge.py    ← 模拟数据源
├── frontend/                ← Vue3 SPA
│   ├── src/                 ← views(8) + components(7) + stores + api + router
│   └── dist/                ← 构建产物（已提交，免 Node 部署）
├── firmware/                ← ESP32-C3 MicroPython
│   ├── main.py / boot.py    ← 入口
│   ├── ap_config.py         ← AP 配网
│   ├── app_config.py        ← 配置读写
│   ├── modbus_gw.py         ← Modbus TCP 主站
│   ├── relay_hw.py          ← GPIO 抽象
│   └── config.json          ← MQTT/WiFi 凭据
├── tools/                   ← modbus_slave_sim / set_modbus / detect_com
└── tests/                   ← 6 单元测试 + e2e/test_e2e_full_chain.py
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

相关文档：[01-快速开始](01-quickstart.md) ｜ [02-架构设计](02-architecture.md) ｜ [05-部署指南](05-deploy.md)
