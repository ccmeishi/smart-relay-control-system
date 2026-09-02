# Day1 · 温湿度感应器模拟器

物联网通信基础阶段，实现 Modbus TCP 采集 + MQTT 上报 + JSON 存储 + 双向命令响应。

## 功能清单

| # | 功能 | 状态 |
|---|------|------|
| 1 | Modbus TCP 周期采集 (功能码 0x03) | ✅ |
| 2 | MQTT 变化上报 + retain | ✅ |
| 3 | JSON 本地存储 (sensor_data.json) | ✅ |
| 4 | 心跳消息 (60s, 数据无变化时) | ✅ |
| 5 | MQTT 遗嘱消息 (LWT) | ✅ |
| 6 | 断线自动重连 | ✅ |
| 7 | write 命令 (功能码 0x06) | ✅ |
| 8 | read / query 命令 | ✅ |

## MQTT Topic

| 用途 | Topic |
|------|-------|
| 数据/心跳/状态上报 | `device/sensor/sevengroup` |
| 命令下发 (write/read/query) | `device/sensor/sevengroup/cmd` |

## Payload 格式（非标准）

```json
// 数据上报
{"type":"data", "temperature":25.3, "humidity":56.7, "registers":[253,567,0,...], "deviceId":"sensor01", "ts":"2026-09-02T12:00:00"}

// 写入命令
{"cmd":"write", "register":0, "value":300}   // 写 reg0 = 30.0°C
```

## 运行

```bash
# 1. 编辑 config.json (确保 mqtt / modbus 配置正确)
# 2. 启动
python sensor_simulator.py
```

## 寄存器映射

| 寄存器偏移 | 名称 | 缩放 | 说明 |
|-----------|------|------|------|
| 0 | temperature | 0.1 | 温度 °C (有符号) |
| 1 | humidity | 0.1 | 湿度 %RH (无符号) |
| 2~9 | - | - | 预留 |
