# Day2 · JetLinks 云平台接入 + 继电器扩展

## 当天目标

从 Day1 的"能跑起来"升级到"接云平台"。学习两种不同数据格式接入 JetLinks 物联网平台，然后扩展出 **4 路继电器控制 + Web UI 面板**，为后续 Day4 平台配置、Day5 ESP32 移植打基础。

## 核心架构

```
┌─────────────┐   Modbus TCP    ┌───────────────────────┐   MQTT JetLinks 格式    ┌──────────┐
│ Day1 温湿度  │ ──reg0=温度──▶ │ relay_simulator_jl.py │ ──────────────────────▶ │          │
│ 模拟器      │ ──reg1=湿度──▶ │   (4路继电器+扩展属性) │   /relay-cc/relaycc/...  │ JetLinks │
│ (端口5502)  │ ──reg2~5=继电器│                       │                          │ 平台     │
└─────────────┘                 └───────────┬───────────┘                          └──────────┘
                                            │
                                   JetLinks 下发命令
                                   (远程控制继电器开关)
```

## 任务 1：两种数据格式接入

### 方式一：非标准 → 标准（EMQX 规则引擎转换）

```
Day1 模拟器 ──原始格式──▶ EMQX ──规则转换──▶ JetLinks
  topic: device/sensor/sevengroup    规则引擎 SQL    topic: /sensor-cc/sensorcc/properties/report
                                      SELECT * FROM "device/sensor/sevengroup"
```

- **设备侧零改动**：保持 Day1 原始报文格式
- EMQX 规则引擎把非标准 payload 映射成 JetLinks 标准格式
- **适用场景**：旧设备不改固件就能接入新平台
- **局限**：只有上行，下行需额外规则或用方式二

### 方式二：标准格式直连（JetLinks 官方协议）

```
sensor_simulator_jl.py ──JetLinks 格式──▶ EMQX ──▶ JetLinks
  topic: /{productId}/{deviceId}/properties/report
```

- 直接按 JetLinks 官方 MQTT 协议上报
- **完整双向通信**：属性上报 + write/read 命令响应
- 完全符合 JetLinks 物模型定义

### Payload 对比

```json
// 方式一（非标准）
{"type":"data","temperature":25.3,"humidity":56.7,...}

// 方式二（JetLinks 标准）
{"timestamp":1725196800000,"messageId":"xxx","properties":{"temperature":25.3,"humidity":56.7}}
```

### 格式对比测试

```powershell
python test_format_compare.py
```

## 任务 2：4 路继电器 + Web UI

### 继电器物模型

| 属性 ID | 名称 | 类型 | 读写 | Modbus 寄存器 |
|---------|------|------|------|--------------|
| relay1 | 继电器1 | int | 读写 | reg2 (0x0002) |
| relay2 | 继电器2 | int | 读写 | reg3 (0x0003) |
| relay3 | 继电器3 | int | 读写 | reg4 (0x0004) |
| relay4 | 继电器4 | int | 读写 | reg5 (0x0005) |
| current | 总电流 | float | 只读 | reg6 (x10 缩放) |
| voltage | 电源电压 | float | 只读 | reg7 (x10 缩放) |

### JetLinks 远程控制流程

```
JetLinks 控制台 → 编辑 relay1 → 输入 1
  → JetLinks 发 MQTT: /relay-cc/relaycc/properties/write
                     {"messageId":"xxx","properties":{"relay1":1}}
  → relay_simulator_jl.py 收到
  → 写 reg2 = 1 (继电器1 吸合)
  → 回复 write/reply: {"messageId":"xxx","success":true,...}
  → JetLinks 更新设备状态 ✅
```

### 继电器 Web UI

```powershell
python relay_ui.py
# 浏览器打开 http://localhost:8081
```

Web UI 功能：
- 4 个继电器开关按钮
- 实时显示电流/电压
- 显示 MQTT 连接状态
- 手动触发"模拟跳闸"测试

## 代码结构

```
day2/
├── relay_simulator_jl.py    ← 继电器 JetLinks 直连模拟器（核心）
├── relay_ui.py              ← 继电器 Web UI（Flask + SocketIO）
├── sensor_simulator_jl.py   ← 温湿度 JetLinks 直连版（方式二）
├── config_relay.json        ← 继电器配置
├── config_jetlinks.json     ← 温湿度配置
├── config_original.json     ← 原始格式配置（Day1 兼容）
├── emqx_rule.sql            ← EMQX 规则引擎 SQL（方式一）
├── test_format_compare.py   ← 格式对比测试
├── requirements.txt         ← Python 依赖列表
├── start_relay.bat          ← 双击启动继电器模拟器 ✅
├── start_sensor.bat         ← 双击启动温湿度模拟器 ✅
├── start_ui.bat             ← 双击启动 Web UI ✅
└── README.md                ← 本文件
```

## 运行步骤

### 准备工作

1. **Day1 模拟器已启动**（端口 5502 有温湿度数据）
2. **JetLinks 平台已创建产品** `relay-cc` + 设备 `relaycc` + 物模型（见 Day4）
3. **EMQX Broker 可达**：`172.16.4.211:9783`

### 启动顺序（3 个终端）

```
终端 1: 双击 day1/start.bat          ← 温湿度 Modbus 从站
终端 2: 双击 day2/start_relay.bat    ← 继电器模拟器（读 Modbus + 上报 JetLinks）
终端 3: 双击 day2/start_ui.bat       ← Web UI，浏览器开 http://localhost:8081
```

### 预期输出（继电器模拟器）

```
继电器模拟器已启动:
  MQTT 直连 JetLinks: 172.16.4.211:9783
  Product: relay-cc  Device: relaycc
  4 路继电器已初始化: [0, 0, 0, 0]
...
[modbus] 读 reg0~7 → [253, 567, 0, 0, 0, 0, 150, 2200]
[mqtt] 上报: {"temperature":25.3,"humidity":56.7,"relay1":0,"relay2":0,...}
```

### 本地测试（不连 JetLinks）

如果只想测试 Modbus 链路，把 `config_relay.json` 里的 `mqtt.host` 改成 `127.0.0.1`，用 `simulator/tools/modbus_slave_sim.py` 起一个本地从站即可。

## 从 Day1 到 Day2 学了什么

| 主题 | Day1 | Day2 |
|------|------|------|
| Modbus | 写从站 | 写**主站**（读 Day1 的从站） |
| MQTT | 自定义 topic | **JetLinks 标准 topic + payload** |
| 云端 | 无 | JetLinks 产品/设备/物模型 |
| 控制 | 无 | 属性 write → Modbus 写寄存器 |
| 界面 | 终端日志 | **Web UI + Flask SocketIO** |

## 与后续 Day 的关系

| Day | 关系 |
|-----|------|
| Day3 | 继电器模拟器继续使用，学习前端独立部署 |
| Day4 | JetLinks 平台配置继电器物模型、规则引擎、告警 |
| Day5 | 继电器逻辑移植到 ESP32 实物（PC 模拟器 → 硬件） |
| Day7 | ESP32 增加 Modbus 网关功能，读 Day1 温湿度上报 JetLinks |
