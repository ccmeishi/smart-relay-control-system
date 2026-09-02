# 智能继电器管控系统 · Smart Relay Control System

> 打通 **Modbus 设备采集 → MQTT Broker → JetLinks 云平台 → 双向远程控制** 全链路的物联网继电器管控方案。以 Python 模拟器为载体，完整实现了从物理寄存器读写、MQTT 消息发布订阅、EMQX 规则引擎格式转换，到 JetLinks 物模型上报与属性下发的端到端闭环。

**当前进度：阶段 2 / 10（Day1 + Day2 已完成，Day3~Day10 持续迭代中）**

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 · 环境准备 | Git 双远程、Python 环境、JetLinks + EMQX 部署 | ✅ |
| 1 · Day1 | Modbus 采集 + MQTT 温湿度传感器模拟器（原始报文） | ✅ |
| 2 · Day2 | JetLinks 两种接入方式 + 继电器远程控制全链路 | ✅ |
| 3 · Day3 | 多通道继电器模拟器（8 路，上报/响应/重连） | 🔜 |
| 4~10 | 固件、后端、前端、大屏、安全、联调、答辩 | 📋 |

---

## ✨ 已实现亮点

- **两种设备接入方式对比落地**：同一台模拟器同时支持 EMQX 规则引擎转换（非标准→标准）与 JetLinks 官方 MQTT 协议直连，完整跑通两种链路并验证优劣
- **继电器远程控制全链路打通**：JetLinks 控制台编辑属性 → MQTT write 命令下发 → Modbus 写寄存器 → 继电器状态变更 → 电流联动（每开一路 +0.5A）→ 设备自动上报，全链路无断点
- **MQTT 可靠性机制完整实现**：Retain 消息保证新订阅者立即获取最新值、遗嘱消息（LWT）异常掉线通知、心跳保活、断线自动重连
- **真实踩坑与问题解决**：JetLinks 物模型标识拼写必须与代码属性名完全一致、EMQX 6.1.4 版本不支持 `json_extract`/`unix_timestamp` 需用最简 SQL、paho-mqtt 回调跨线程操作 Modbus 需通过 queue 解耦

---

## 🏗️ 系统架构

![项目总览图](docs/images/项目总览图.png)

```
┌────────────────────┐     ┌─────────────────┐     ┌─────────────────────┐
│  Modbus TCP 从站   │────▶│  MQTT Broker    │────▶│  JetLinks 物联网    │
│  (真实设备/模拟器)  │◀────│  EMQX 9783      │◀────│  平台 (MQTT 客户端) │
└────────────────────┘     └─────────────────┘     └─────────────────────┘
                                    │
                         ┌──────────┴──────────┐
                         ▼                     ▼
                  规则引擎 (方式一)      标准直连 (方式二)
                  SELECT * FROM topic    /{productId}/{deviceId}/
                  ${payload.temperature} properties/report
```

### 两种接入方式对比

| | 方式一：EMQX 规则转换 | 方式二：JetLinks 直连 |
|---|---|---|
| 设备侧改动 | **零改动**，保持原始报文格式 | 需按 JetLinks 官方协议上报 |
| 双向通信 | ❌ 只有上行 | ✅ 完整 write/read 响应 |
| 适用场景 | 旧设备不改固件快速接入 | 正规生产设备首选方案 |
| 我们的实现 | `emqx_rule.sql` + Day1 模拟器 | `sensor_simulator_jl.py` / `relay_simulator_jl.py` |

---

## 🔧 关键技术实现

### Day1 · 温湿度传感器（非标准报文）

```
寄存器布局：reg0 = temperature (×0.1, 有符号)  reg1 = humidity (×0.1, 无符号)
MQTT 上报 topic：device/sensor/sevengroup
MQTT 命令 topic：device/sensor/sevengroup/cmd  ← write / read / query
```

**核心设计**：5 秒轮询 Modbus → 变化检测 → MQTT 上报；值无变化时每 60 秒发心跳；遗嘱主题为 `device/sensor/online`，值 `"offline"`。跨线程安全：paho-mqtt 的 `on_message` 回调在网络线程执行，用 `queue.Queue` 把命令传给主循环处理 Modbus 操作。

### Day2 · JetLinks 接入 + 继电器控制

```
继电器物模型 (product_id=relay-cc, device_id=relaycc)：
┌────────┬─────────┬───────┬──────┬──────────┬─────────────────┐
│ 标识    │ 名称     │ 类型   │ 读写  │ Modbus   │ 说明             │
├────────┼─────────┼───────┼──────┼──────────┼─────────────────┤
│ relay1 │ 继电器1  │ int   │ 读写  │ reg2     │ 0=关 / 1=开      │
│ relay2 │ 继电器2  │ int   │ 读写  │ reg3     │                  │
│ relay3 │ 继电器3  │ int   │ 读写  │ reg4     │                  │
│ relay4 │ 继电器4  │ int   │ 读写  │ reg5     │                  │
│ current│ 总电流   │ float │ 只读  │ reg6     │ ×0.1, 联动计算   │
│ voltage│ 电源电压 │ float │ 只读  │ reg7     │ ×0.1, 218~222V  │
└────────┴─────────┴───────┴──────┴──────────┴─────────────────┘
```

**远程控制链路（已完整验证）**：

```
JetLinks 控制台编辑 relay1=1
  → MQTT 下发: /relay-cc/relaycc/properties/write
    payload: {"messageId":"xxx","properties":{"relay1":1}}
  → relay_simulator_jl.py 收到 → Modbus write_register(2, 1)
  → Modbus 从站自动联动: 电流 += 0.5A
  → 回复 JetLinks: /relay-cc/relaycc/properties/write/reply
    payload: {"messageId":"xxx","success":true,"properties":{"relay1":1}}
  → 模拟器主动上报新状态 → JetLinks 界面刷新
```

### EMQX 规则引擎（方式一）

```sql
-- EMQX 6.1.4 不支持 unix_timestamp / json_extract / IS NOT NULL
-- 最简可用版本
SELECT * FROM "device/sensor/sevengroup"
```

动作配置：消息重发布到 `/sensor-cc/sensorcc/properties/report`，Payload 模板提取字段：
```json
{
  "timestamp": ${ts},
  "messageId": "${messageId}",
  "properties": {
    "temperature": ${payload.temperature},
    "humidity": ${payload.humidity}
  }
}
```

---

## 🧱 技术栈

| 类别 | 技术 |
|---|---|
| 设备端 | Python 3.10, pymodbus 3.6.9, paho-mqtt 1.6.1 |
| 通信 | Modbus TCP (功能码 0x03 / 0x06), MQTT v3.1.1 (QoS 0/1, Retain, LWT) |
| 云平台 | JetLinks (开源 IoT 平台, MQTT 接入模式), EMQX 6.1.4 (Broker + 规则引擎) |
| 测试 | MQTTX, 本地 Modbus 从站模拟器 |
| 协作 | Git + GitHub/Gitee 双远程, Markdown 文档 |

---

## 📂 项目结构

```
smart-relay-control-system/
├── simulator/
│   ├── day1/                        # 阶段1: 温湿度传感器 (原始报文) ✅
│   │   ├── sensor_simulator.py       # Modbus 采集 + MQTT 上报 + 双向命令
│   │   ├── config.json
│   │   ├── bom.txt
│   │   └── README.md
│   ├── day2/                        # 阶段2: JetLinks 接入 + 继电器 ✅
│   │   ├── sensor_simulator_jl.py    # 温湿度 JetLinks 直连版
│   │   ├── relay_simulator_jl.py      # 继电器 JetLinks 直连版
│   │   ├── config_relay.json          # 继电器配置 (product_id / register_map)
│   │   ├── emqx_rule.sql              # EMQX 规则引擎 SQL
│   │   ├── test_format_compare.py     # 两种格式对比测试
│   │   └── README.md
│   ├── day3/...day10/               # 后续阶段待实现 🔜
│   ├── tools/
│   │   └── modbus_slave_sim.py        # 本地 Modbus TCP 从站模拟器
│   └── README.md
├── docs/images/                      # 架构图
├── backend/ / frontend/ / firmware/  # 待补充
├── .gitignore
├── LICENSE
└── README.md
```

---

## 🚀 快速上手

```bash
# 1. 安装依赖
pip install pymodbus==3.6.9 paho-mqtt==1.6.1

# 2. 启动本地 Modbus 从站 (可选, 无真实设备时用)
python simulator/tools/modbus_slave_sim.py

# 3. 启动继电器模拟器 (Day2, JetLinks 直连)
#    先确认 config_relay.json 里 broker / product_id / device_id 配置正确
python simulator/day2/relay_simulator_jl.py

# 4. 启动温湿度模拟器 (Day1, 原始报文)
python simulator/day1/sensor_simulator.py
```

JetLinks 侧需提前创建：
- 产品 `relay-cc` + 设备 `relaycc` + 物模型（relay1~4 / current / voltage）
- 产品 `sensor-cc` + 设备 `sensorcc` + 物模型（temperature / humidity）

---

## 📄 License

MIT License. See [LICENSE](./LICENSE) for details.
