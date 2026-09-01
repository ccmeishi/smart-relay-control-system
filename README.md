# smart-relay-control-system

温湿度感应器模拟器 — 基于 Modbus TCP 采集 + MQTT 上报的 IoT 终端模拟系统

## 项目简介

使用 Python 实现温湿度感应器模拟器，通过 Modbus TCP 协议从从站采集寄存器数据，
存储到 JSON 文件，当值发生变化时通过 MQTT 协议上报到服务器。
支持双向通信：可通过 MQTT 下发命令读写 Modbus 寄存器。

## 功能特性

| 功能 | 说明 |
|------|------|
| Modbus TCP 采集 | 功能码 0x03 读保持寄存器 0x0000~0x0009，周期可配置 |
| JSON 存储 | 采集值保存在 sensor_data.json，作为"上一次的值"用于变化检测 |
| 变化上报 | 值发生变化时立即更新 JSON 并发布 MQTT 消息（retain 保留消息） |
| 心跳机制 | 数据无变化时每 60 秒发一次心跳，证明设备在线 |
| 遗嘱机制（LWT） | 异常掉线时 broker 自动发布 offline，正常上线发布 online |
| 写寄存器 | 订阅命令主题，收到 write 命令用功能码 0x06 写入并回 write_ack |
| 断线重连 | Modbus 和 MQTT 均支持自动重连 |

## 项目结构

```
smart-relay-control-system/
├── day1/                       # Day1 温湿度感应器模拟器
│   ├── sensor_simulator.py     # 主程序：Modbus采集 → JSON存储 → MQTT上报
│   ├── modbus_slave_sim.py     # Modbus从站模拟器（联调测试用）
│   └── config.json             # 配置文件（Modbus/MQTT/寄存器映射）
├── .gitignore
├── LICENSE
└── README.md
```

## 快速开始

### 环境依赖

- Python 3.8+
- pymodbus==3.6.9
- paho-mqtt==1.6.1

```bash
pip install pymodbus==3.6.9 paho-mqtt==1.6.1
```

### 配置说明

所有参数集中在 `config.json` 中，修改配置无需改代码：

```json
{
  "modbus": {
    "host": "192.168.20.59",
    "port": 5502,
    "unit_id": 1,
    "register_start": 0,
    "register_count": 10,
    "poll_interval": 5
  },
  "mqtt": {
    "host": "172.16.4.211",
    "port": 9783,
    "username": "test",
    "password": "123456",
    "client_id": "sensor_public_demo",
    "topic_data": "device/sensor/temp",
    "topic_cmd": "device/sensor/temp/cmd"
  },
  "register_map": {
    "0": { "name": "temperature", "scale": 0.1, "signed": true, "unit": "C" },
    "1": { "name": "humidity", "scale": 0.1, "signed": false, "unit": "%RH" }
  }
}
```

| 配置项 | 说明 |
|--------|------|
| modbus.host/port | Modbus 从站地址和端口 |
| modbus.register_start/count | 寄存器起始地址和数量（0x0000~0x0009） |
| modbus.poll_interval | 采集轮询周期（秒） |
| mqtt.host/port | MQTT 服务器地址和端口 |
| mqtt.topic_data | 数据上报主题 |
| mqtt.topic_cmd | 命令下发主题 |
| register_map | 寄存器含义映射：名称/缩放/有符号/单位 |

### 运行方式

**方式一：连接实验室从站**

```bash
python sensor_simulator.py
```

**方式二：本机模拟从站联调（无实验室环境时）**

```bash
# 终端1：启动从站模拟器（监听 0.0.0.0:5502）
python modbus_slave_sim.py

# 终端2：启动主程序（config.json 中 host 改为 127.0.0.1）
python sensor_simulator.py
```

## MQTT 通信协议

### 上报 Payload 格式（自行设计）

**数据上报：**
```json
{
  "type": "data",
  "deviceId": "sensor_public_demo",
  "temperature": 25.3,
  "humidity": 56.7,
  "registers": [253, 567, 0, 0, 0, 0, 0, 0, 0, 0],
  "ts": "2026-09-01T12:00:00"
}
```

**其他消息类型：**

| type | 触发条件 | 说明 |
|------|---------|------|
| data | 寄存器值变化 | 数据上报，retain 保留消息 |
| heartbeat | 每 60 秒 | 心跳，证明设备在线 |
| online | MQTT 连接成功 | 上线通知，retain |
| offline | 异常断线 | 遗嘱消息（LWT），broker 自动发布 |
| write_ack | 写入命令成功 | 写寄存器确认 |
| error | 操作失败 | 错误详情 |

### 下发命令格式

往命令主题 `device/sensor/temp/cmd` 发送 JSON：

```json
{"cmd": "write", "register": 2, "value": 42}
```

| 命令 | 说明 |
|------|------|
| write | 写入指定寄存器（register=偏移, value=值），回 write_ack |
| read | 立即采集一次并强制上报（无论值是否变化） |
| query | 查询 JSON 中缓存的最后一次值并上报 |

## 技术要点

- **Modbus TCP**：功能码 0x03 读保持寄存器 / 0x06 写单个寄存器
- **MQTT QoS**：关键消息（上线/遗嘱/write_ack）用 QoS 1 保证送达；心跳用 QoS 0 省流量
- **Retain 保留消息**：data/online/offline 设为 retain，新订阅者上线即得最新状态
- **遗嘱（LWT）**：连接时预注册遗嘱，异常掉线时 broker 自动发布 offline
- **断线重连**：Modbus 和 MQTT 均支持自动重连
- **寄存器越界保护**：write 命令检查偏移是否在本组范围内，拒绝越界写入

## 技术栈

| 层 | 技术 | 用途 |
|----|------|------|
| 感知层 | Modbus TCP 从站 | 温湿度寄存器存储 |
| 网络层 | Modbus TCP / TCP/IP | 数据采集与设备控制 |
| 平台层 | EMQX MQTT Broker | 消息中间件 |
| 应用层 | MQTTX / Python paho-mqtt | 订阅与命令下发 |

## 依赖

- [pymodbus](https://github.com/pymodbus-dev/pymodbus) == 3.6.9 — Modbus TCP 客户端
- [paho-mqtt](https://github.com/eclipse/paho.mqtt.python) == 1.6.1 — MQTT 客户端
