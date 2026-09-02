# Day2 · JetLinks 云平台接入 + 继电器扩展

## 任务 1：两种数据格式接入

### 方式一：非标准格式 → 标准格式（EMQX 规则转换）

```
Day1 模拟器 ──原始格式──▶ EMQX Broker ──规则转换──▶ JetLinks
  topic: device/sensor/sevengroup    规则引擎            topic: /sensor-cc/sensorcc/properties/report
```

- **设备侧代码零改动**，保持 Day1 原始报文格式
- EMQX 规则引擎 SQL: `SELECT * FROM "device/sensor/sevengroup"`
- 动作: 消息重发布到 JetLinks topic，Payload 模板提取字段
- **特点**: 旧设备不改固件即可接入新平台
- **局限**: 只有上行，下行需额外规则或用方式二

### 方式二：标准格式直连（JetLinks 官方协议）

```
sensor_simulator_jl.py ──JetLinks 格式──▶ EMQX Broker ──▶ JetLinks
  topic: /{productId}/{deviceId}/properties/report
```

- 模拟器直接按 JetLinks 官方 MQTT 协议上报
- 完整双向通信（属性上报 + write/read 命令响应）
- **特点**: 完全符合 JetLinks 物模型定义，支持双向控制

### 格式对比

```
方式一 Payload (非标准):
  {"type":"data","temperature":25.3,"humidity":56.7,...}

方式二 Payload (JetLinks 标准):
  {"timestamp":1725196800000,"messageId":"xxx","properties":{"temperature":25.3,"humidity":56.7}}
```

### 测试

```bash
python test_format_compare.py
```

---

## 任务 2：继电器扩展属性 + 平台控制

### 继电器物模型定义

| 属性 ID | 名称 | 数据类型 | 读写 | Modbus 寄存器 |
|---------|------|----------|------|--------------|
| relay1 | 继电器1 | int | 读写 | reg2 (0x0002) |
| relay2 | 继电器2 | int | 读写 | reg3 (0x0003) |
| relay3 | 继电器3 | int | 读写 | reg4 (0x0004) |
| relay4 | 继电器4 | int | 读写 | reg5 (0x0005) |
| current | 总电流 | float | 只读 | reg6 (x10) |
| voltage | 电源电压 | float | 只读 | reg7 (x10) |

### JetLinks 远程控制流程

```
JetLinks 控制台
  → 编辑 relay1 属性 → 输入 1 → 确定
  → JetLinks 发 MQTT write 命令
    topic: /relay-cc/relaycc/properties/write
    payload: {"messageId":"xxx","properties":{"relay1":1}}
  → relay_simulator_jl.py 收到
  → Modbus 写 reg2 = 1
  → 回复 write/reply
    topic: /relay-cc/relaycc/properties/write/reply
    payload: {"messageId":"xxx","success":true,"properties":{"relay1":1}}
  → JetLinks 更新设备状态
  → 模拟器自动上报新状态
```

### 运行继电器模拟器

```bash
# 1. 确保 JetLinks 已创建产品 relay-cc + 设备 relaycc + 物模型
# 2. 确保 EMQX Broker 可达
# 3. 启动
python relay_simulator_jl.py
```

### 本地测试

```bash
# 终端 1: 启动本地 Modbus 从站
cd simulator/tools
python modbus_slave_sim.py

# 终端 2: 改 config_relay.json host 为 127.0.0.1 后启动
python relay_simulator_jl.py
```

## 文件清单

| 文件 | 说明 |
|------|------|
| `sensor_simulator_jl.py` | 温湿度 JetLinks 直连版 (方式二) |
| `relay_simulator_jl.py` | 继电器 JetLinks 直连版 |
| `config_jetlinks.json` | 温湿度配置 |
| `config_relay.json` | 继电器配置 |
| `config_original.json` | 原始格式配置 |
| `emqx_rule.sql` | EMQX 规则引擎配置 (方式一) |
| `test_format_compare.py` | 格式对比测试脚本 |
| `requirements.txt` | 依赖列表 |
