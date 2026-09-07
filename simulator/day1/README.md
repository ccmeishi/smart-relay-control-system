# Day1 · 温湿度感应器模拟器

## 当天目标

实现一个运行在 PC 上的 Modbus TCP 从站模拟器，模拟温湿度传感器，验证 Modbus 协议基本通信 + MQTT 上报。这是整个项目的第一块积木——后续 Day2 继电器模拟器、Day7 ESP32 网关都依赖这个从站模拟器来测试。

## 功能清单

| # | 功能 | 说明 |
|---|------|------|
| 1 | Modbus TCP 从站 | 监听 0.0.0.0:5502，unit_id=7 |
| 2 | 温湿度寄存器漂移 | reg0/reg1 每 2 秒随机变化 ±1 |
| 3 | MQTT 周期上报 | 每 5 秒上报一次（即使数据没变化） |
| 4 | MQTT 变化上报 | 数据变化时立即上报 |
| 5 | JSON 本地存储 | sensor_data.json 记录每次上报 |
| 6 | 心跳消息 | 60 秒无变化时发心跳 |
| 7 | 遗嘱消息 (LWT) | 异常断开时 Broker 广播遗嘱 |
| 8 | 断线重连 | MQTT 断开后自动重连 |
| 9 | write 命令 | 支持 Modbus 功能码 0x06 写寄存器 |
| 10 | read / query 命令 | MQTT cmd 下行命令响应 |

## 代码结构

```
day1/
├── sensor_simulator.py   ← 主程序（Modbus 从站 + MQTT 上报）
├── config.json           ← 配置文件（Modbus/MQTT 参数）
├── requirements.txt      ← Python 依赖
├── bom.txt               ← 物料清单（硬件参考，本项目 PC 端不用）
├── start.bat             ← 🆕 双击启动脚本
└── README.md             ← 本文件
```

### sensor_simulator.py 核心逻辑

```python
# 启动流程
1. 加载 config.json → 获取 Modbus/MQTT 配置
2. 创建 Modbus TCP 从站 → 注册寄存器表
3. 连接 MQTT Broker → 注册回调
4. 进入主循环:
   ├── 处理 Modbus 请求（阻塞，pymodbus 库内部轮询）
   ├── 处理 MQTT 下行命令
   ├── 温湿度随机漂移
   └── 周期性检查上报条件
```

### config.json 配置说明

```json
{
  "modbus": {
    "host": "0.0.0.0",
    "port": 5502,
    "unit_id": 7
  },
  "mqtt": {
    "host": "172.16.4.211",
    "port": 9783,
    "user": "test",
    "pass": "123456",
    "client_id": "sensor01",
    "topic_data": "device/sensor/sevengroup",
    "topic_cmd": "device/sensor/sevengroup/cmd"
  }
}
```

## 运行步骤

### 方式 1：双击启动

```
双击 start.bat
```

### 方式 2：手动运行

```powershell
# 1. 安装依赖（首次）
pip install pymodbus paho-mqtt

# 2. 确认 config.json 里的 MQTT 配置正确
#    host: 172.16.4.211  port: 9783  user/pass: test/123456

# 3. 启动
python sensor_simulator.py
```

### 预期输出

```
Modbus TCP 从站模拟器已启动: 0.0.0.0:5502 (unit_id=7)
MQTT 已连接 172.16.4.211:9783
  reg0 温度  (x10, 起始 25.3°C)
  reg1 湿度  (x10, 起始 56.7%RH)
...
[modbus] 收到读 reg0~1 → 返回 [253, 567]
[mqtt] 上报数据: {"type":"data","temperature":25.3,...}
```

## 寄存器映射

| 寄存器偏移 | 名称 | 格式 | 缩放 | 初始值 |
|-----------|------|------|------|--------|
| reg0 | temperature | uint16 | 0.1 | 253 (25.3°C) |
| reg1 | humidity | uint16 | 0.1 | 567 (56.7%RH) |
| reg2~9 | 预留 | uint16 | - | 0 |

### 用 Modbus Poll 测试

1. 打开 Modbus Poll → Connection → Connect
2. 选 TCP/IP → Host: 127.0.0.1 Port: 5502
3. Setup → Slave ID: 7，功能码 03 (Read Holding Registers)
4. Start Address: 0，Quantity: 2
5. 应看到 reg0 和 reg1 的值，且每 2 秒变化

## MQTT Payload 格式（非标准）

```json
// 数据上报
{
  "type": "data",
  "temperature": 25.3,
  "humidity": 56.7,
  "registers": [253, 567, 0, 0, ...],
  "deviceId": "sensor01",
  "ts": "2026-09-02T12:00:00"
}

// 心跳
{"type": "heartbeat", "uptime": 3600, "deviceId": "sensor01"}

// 写入命令
{"cmd": "write", "register": 0, "value": 300}
```

## 与后续 Day 的关系

| Day | 如何使用 Day1 的模拟器 |
|-----|----------------------|
| Day2 | `relay_simulator_jl.py` 读 Day1 模拟器的 Modbus 寄存器 |
| Day7 | ESP32 固件作为 Modbus 主站读 Day1 模拟器 |

Day1 模拟器是 PC 端模拟的"传感器盒子"，后续所有涉及 Modbus 采集的开发都可以用它测试，不需要实物传感器。
