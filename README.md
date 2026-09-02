# 智能继电器控制系统（Smart Relay Control System）

一个覆盖 **设备 → 协议 → 云平台 → 业务平台 → 大屏应用** 全链路的物联网继电器管控系统，实现设备**远程控制、虚拟化管理、权限管控与可视化展示**。

---

## 本文档的目录

> 本教程按推进顺序阅读：**先环境 → 再项目介绍 / 接口文档 → 最后是按天学习内容**。

- [1. 项目简介](#1-项目简介)
- [2. 总体架构](#2-总体架构)
- [3. 端到端业务流程](#3-端到端业务流程)
- [4. 核心能力（技术要点）](#4-核心能力技术要点)
- [5. 技术栈](#5-技术栈)
- [6. 项目结构](#6-项目结构)
- [7. 学习路线](#7-学习路线)
- [8. 快速开始](#8-快速开始)
- [9. 许可与声明](#9-许可与声明)

---

## 1. 项目简介

本系统面向智能继电器设备，提供从硬件接入到云端管理、再到前端大屏展示的完整闭环。核心目标是打通「设备端 → 局域网/公网 → 云平台 → 业务平台 → 可视化大屏」全链路，让真实继电器与虚拟设备都能被统一管理和控制，并支持细粒度的权限与可控设备管理。

---

## 2. 总体架构

| 层级 | 说明 |
| --- | --- |
| **设备层** | 真实继电器设备（单片机控制、传感采集、Wi-Fi/Ethernet 联网）以及参数可配置的模拟/虚拟设备 |
| **协议与网络层** | MQTT / Modbus RTU（RS485）、自行定义协议；局域网内 Mesh，公网 4G/Wi-Fi 上云 |
| **云平台层** | JetLinks 开源物联网平台（连接与设备管理）：设备接入、认证授权、物模型管理、规则引擎、数据存储 |
| **业务平台层（后端）** | API 网关、用户服务、权限服务、设备服务、控制服务；MySQL 数据存储、Redis 缓存；对外提供 RESTful API / WebSocket / SSE |
| **前端 & 可视化层** | Vue3 + Element Plus 实现设备/流程/虚拟化管理、控制台控制、实时状态；ECharts / DataV 大屏可视化 |
| **用户层** | 运维工程师、管理员、普通用户（平台/APP/大屏多端） |

---

## 3. 端到端业务流程

1. **用户操作**：用户在前端点击「开/关 CH1」
2. **后端接收请求**：前端 → 后端 API 网关
3. **权限校验**：RBAC 权限校验通过
4. **生成命令**：由平台生成控制指令
5. **下发布到平台**：通过 JetLinks 下发指令
6. **设备接收并执行**：继电器执行开/关
7. **状态回传**：设备将状态回传（ON/OFF）
8. **平台处理**：JetLinks 处理并同步数据
9. **业务平台同步**：业务平台状态更新并缓存状态
10. **前端订阅刷新**：通过 WebSocket 推送，前端状态刷新

---

## 4. 核心能力（技术要点）

- **真实设备接入与模拟**：真实继电器接入 + 虚拟设备模拟，模拟与测试能力
- **多协议支持**：MQTT / Modbus RTU / 自定义协议
- **云端与数据**：JetLinks 平台（连接+设备+物模型）、MySQL 持久化、Redis 缓存
- **业务与应用**：权限与可控设备、虚拟化管理、设备控制、状态实时同步
- **安全与权限**：RBAC 权限模块、可控设备管理、登录鉴权、数据存储加密
- **实时交互**：WebSocket / SSE 实时推送

---

## 5. 技术栈

| 类别 | 技术 |
| --- | --- |
| 设备端 | ESP32、C/C++、Python |
| 通信协议 | MQTT、Modbus TCP/RTU |
| 云平台 | JetLinks（开源物联网平台）、EMQX（MQTT Broker） |
| 数据库 | MySQL、Redis |
| 前端 | Vue3、Element Plus |
| 可视化 | ECharts、DataV |
| 部署 | Docker、Nginx |

---

## 6. 项目结构

```
smart-relay-control-system/
├── simulator/                 # 模拟器 (Python)
│   ├── day1/                  # 阶段1: 温湿度传感器模拟器 (原始报文)
│   ├── day2/                  # 阶段2: JetLinks 接入 + 继电器扩展
│   │   ├── sensor_simulator_jl.py   # 温湿度 JetLinks 直连版
│   │   ├── relay_simulator_jl.py     # 继电器 JetLinks 直连版 ✨
│   │   ├── emqx_rule.sql            # EMQX 规则引擎配置 (方式一)
│   │   ├── test_format_compare.py   # 两种格式对比测试脚本
│   │   └── config_*.json            # 各种配置文件
│   ├── tools/                 # 辅助工具 (Modbus 从站模拟器等)
│   └── requirements.txt
├── docs/                      # 文档
│   └── images/                # 架构图 / 流程图等图片资源
├── firmware/                  # 设备固件（ESP32）
├── backend/                   # 后端服务（API 网关、业务服务）
├── frontend/                  # 前端（Vue3 + Element Plus）
├── src/                       # 源文件
├── tools/                     # 工具脚本
├── .gitignore
├── README.md                  # 本文档
└── bom.txt
```

---

## 7. 学习路线

### 7.1 阶段 0 · 环境准备

> 开发环境安装与项目创建（环境部署）。涵盖开发工具/IDE 选择、环境安装、平台账号注册、项目仓库创建、环境配置、环境验证、项目初始化与首次提交。

### 7.2 阶段 1 · 物联网通信基础（Day1）

- **Modbus TCP 采集**：周期读取保持寄存器
- **MQTT 上报**：变化检测 + retain 消息 + 断线重连
- **JSON 存储**：本地持久化最新值
- **心跳 / 遗嘱消息**：证明在线与异常掉线通知
- **双向命令**：订阅 cmd topic 响应 write/read/query

> 详见 [simulator/day1/README.md](simulator/day1/README.md)

### 7.3 阶段 2 · JetLinks 云平台接入（Day2）

- **方式一（非标准格式 → 标准格式）**：EMQX 规则引擎转换 Day1 原始报文为 JetLinks 官方格式
- **方式二（标准格式直连）**：模拟器直接按 JetLinks 官方协议上报属性
- **继电器扩展**：在物模型中新增继电器开关属性，实现远程控制
- **扩展属性定义**：电流、电压等监测属性

> 详见 [simulator/day2/README.md](simulator/day2/README.md)

---

## 8. 快速开始

### 8.1 环境要求

- Python 3.10+
- Git（含常用配置：`user.name`、`user.email`）
- MQTTX（测试工具）
- JetLinks 云平台（部署或可用实例）
- EMQX Broker（MQTT 消息服务器）

### 8.2 安装依赖

```bash
pip install pymodbus==3.6.9 paho-mqtt==1.6.1
```

### 8.3 运行 Day1 温湿度模拟器

```bash
cd simulator/day1
python sensor_simulator.py
```

### 8.4 运行 Day2 继电器模拟器

```bash
cd simulator/day2
python relay_simulator_jl.py
```

### 8.5 本地测试（无真实 Modbus 设备时）

```bash
# 启动本地 Modbus 从站模拟器
cd simulator/tools
python modbus_slave_sim.py

# 然后改 day2/config_relay.json 里 host 为 127.0.0.1
```

---

## 9. 许可与声明

本仓库为小组实验项目，最终版权与许可信息将随项目完善补充。
