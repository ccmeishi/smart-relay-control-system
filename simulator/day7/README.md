# Day7 · Modbus 采集网关

## 当天目标

在 Day5 继电器固件基础上，让 ESP32 同时具备 **Modbus TCP 主站**能力——主动去读 PC 上跑的 Day1 温湿度模拟器（或其他 Modbus 从站），把采到的数据合并进 JetLinks MQTT 上报，实现 **"继电器 + 温湿度" 一个设备同时管理**。

## 最终架构

```
┌─────────────┐  Modbus TCP    ┌─────────────────────────┐  MQTT JetLinks   ┌──────────┐
│ Day1 温湿度  │ ←──读 reg0~1── │ ESP32-C3                │ ──────────────▶ │          │
│ 模拟器      │               │                         │                 │          │
│ 192.168.30  │               │  modbus_gw.poll_one()   │  properties/    │ JetLinks │
│   .85:5502  │               │  (时间片,不阻塞)         │  report          │ 平台     │
│ unit_id=7   │               │                         │                 │          │
└─────────────┘               │  + relay_hw (GPIO)      │  function/      │          │
                              │    继电器1~4 本地控制   │  invoke ←────── │          │
                              └─────────────────────────┘                 └──────────┘
```

## 新增/修改文件

| 文件 | 状态 | 行数 | 说明 |
|------|------|------|------|
| `modbus_gw.py` | 🆕 新增 | 324 | Modbus TCP 主站 + 时间片轮询调度器 |
| `app_config.py` | 修改 | +8 | DEFAULTS 新增 `modbus_enabled` / `modbus_slaves` |
| `ap_config.py` | 修改 | +30 | 配网页面新增 Modbus 采集配置卡片；修复 `ensure_ascii=False` 兼容 |
| `main.py` | 修改 | +15 | 导入 modbus_gw、合并 properties()、mqtt_loop() 插入 poll_one() |

### modbus_gw.py 核心设计

#### 1. 时间片轮询（不阻塞主循环）

```python
# main.py 主循环
while True:
    mqtt_client.check_msg()   # 收 MQTT 命令
    modbus_gw.poll_one()      # ← 每次只采 1 个过期的点（≤100ms）
    mqtt_client.ping()
    check_buttons()
    time.sleep(0.1)

# poll_one() 内部:
# - 遍历所有 slave → 所有 point
# - 找 next_due ≤ now 的那个
# - 只采这 1 个，采完就返回
# - 下次 poll_one() 再找下一个
```

**为什么用时间片而不是一次性全采？** ESP32 是单线程 MicroPython，如果一次采多个从站（TCP 连接 + 请求 + 响应），可能花几秒，期间按钮不响应、MQTT 消息不处理。时间片保证每次调用不超过 ~100ms，继电器控制永远优先。

#### 2. 锚点调度（防漂移积累）

```python
# ❌ 错误：会漂移
next_due += period    # 实际执行时间 = 计划时间 + 上一次的延迟

# ✅ 正确：锚点到执行时刻
next_due = ticks_add(now, period)    # 从"此刻"重新算下一次
```

#### 3. 冷却防雪崩

```python
# 同一个从站连续失败 3 次
# → 标记为冷却，30 秒内 poll_one() 看到就跳过（零阻塞）
# → 30 秒后自动重试 1 次
```

#### 4. Modbus TCP 帧编解码

```
MBAP 头: [事务ID(2)][协议ID(2)][长度(2)][单元ID(1)]
PDU:     [功能码(1)][起始地址(2)][寄存器数(2)]

响应:
MBAP 头 + [功能码(1)][字节数(1)][寄存器值...]
```

支持数据类型：`uint16`, `int16`, `uint32`, `int32`, `float_be`（大端浮点）

#### 5. scale 缩放

```json
{"addr": "0x0000", "key": "temperature", "scale": 0.1}
// 寄存器值 253 → 253 × 0.1 = 25.3°C
```

## 代码结构

```
day7/
├── esp32_firmware/           ← Day7 固件文件（增量）
│   ├── modbus_gw.py             ← 🆕 Day7 新增
│   ├── main.py                  ← 修改 (插入 poll_one)
│   ├── app_config.py            ← 修改 (新增 Modbus 默认值)
│   ├── ap_config.py             ← 修改 (新增 Modbus 配置卡片)
│   └── 其他文件（day5 不变）
├── upload_modbus.bat          ← 🆕 增量上传脚本
├── start_modbus_sim.bat       ← 🆕 启动 PC 端 Modbus 从站
├── start_serial.bat           ← 🆕 串口监控（自动检测 COM 口）
└── README.md                  ← 本文件
```

## 运行步骤

### 准备工作

1. **Day5 固件已运行**（继电器正常，WiFi/MQTT 已连上）
2. **PC 和 ESP32 在同一局域网**（ping 通）
3. **Day1 模拟器或 modbus_slave_sim.py 已启动**（端口 5502，unit_id=7）

### 步骤 1：PC 端启动 Modbus 从站

```
双击 start_modbus_sim.bat
```

或手动：
```powershell
cd simulator\tools
python modbus_slave_sim.py 5502 7
```

### 步骤 2：上传 Day7 增量文件

```
双击 upload_modbus.bat
```

或手动：
```powershell
python -m mpremote connect COM5 cp esp32_firmware\modbus_gw.py :/modbus_gw.py
python -m mpremote connect COM5 cp esp32_firmware\app_config.py :/app_config.py
python -m mpremote connect COM5 cp esp32_firmware\ap_config.py :/ap_config.py
python -m mpremote connect COM5 cp esp32_firmware\main.py :/main.py
python -m mpremote connect COM5 reset
```

### 步骤 3：配置 Modbus 采集

方式 A：长按 SW1 进入 AP 配网 → 浏览器开 192.168.4.1 → Modbus 卡片填：
```json
[
  {
    "name": "温湿度传感器",
    "host": "192.168.30.85",
    "port": 5502,
    "unit_id": 7,
    "points": [
      {"addr": "0x0000", "key": "temperature", "period_ms": 3000, "count": 1, "type": "uint16", "scale": 0.1},
      {"addr": "0x0001", "key": "humidity",    "period_ms": 5000, "count": 1, "type": "uint16", "scale": 0.1}
    ]
  }
]
```

方式 B：通过串口 exec 设置（不推荐，会中断 main.py）

### 步骤 4：串口监控验证

```
双击 start_serial.bat
```

预期开机日志：
```
[boot] MicroPython v1.29.0 on 2026-09-02; ESP32-C3
[main] 继电器硬件初始化: 4 路
[main] 连接 Office-WiFi ...
[main] WiFi OK: 192.168.30.145
[main] MQTT 已连接 ✅
[main] Modbus 网关已启动, 采集点: 2
...
[modbus] temperature = 26.6 (scale=0.1, reg=[266])
[modbus] humidity    = 58.3 (scale=0.1, reg=[583])
[mqtt] properties/report: {"relay1":0,"relay2":0,"temperature":26.6,"humidity":58.3,...}
```

### 步骤 5：JetLinks 验证

JetLinks 产品 `relay-cc` 物模型里：
- temperature / humidity → 数据类型选 **double（双精度浮点）**
- 设备详情 → 属性 → 应能看到实时更新

## Day5 vs Day7 对比

| 对比项 | Day5 | Day7 |
|--------|------|------|
| Modbus 角色 | 无 | **主动主站**读外部从站 |
| 继电器控制 | ✅ | ✅（**完全不变**，互不影响） |
| 上报字段 | relay1~4 | relay1~4 + temperature + humidity |
| 配网页面 | WiFi + MQTT | WiFi + MQTT + **Modbus 配置卡片** |
| 按钮长按 | 正常 | 正常（poll_one 不阻塞） |
| 新增代码量 | — | +409 行 |

## 验收清单

- [ ] PC 启动 modbus_slave_sim.py 5502 7
- [ ] 板子串口看到 `Modbus 网关已启动, 采集点: N`
- [ ] 串口周期性输出 `[modbus] xxx = N.N`（带 scale 缩放值）
- [ ] 采集运行时按 SW1 → 继电器立即切换（**非阻塞验证**）
- [ ] JetLinks 物模型 temperature/humidity 类型已改为 double
- [ ] JetLinks 设备属性页面能看到实时温湿度更新
- [ ] PC 上 `netstat -ano | findstr "5502"` 确认 ESP32 有 TCP 连接过来

## 故障排查

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| 没有 `Modbus 网关已启动` 日志 | modbus_enabled 未开启 | 重进 AP 配网，检查 Modbus 配置 |
| 只有冷却跳过日志 `[modbus] 从站冷却中` | 从站 IP 不对或 PC 上模拟器没跑 | 检查 host 和 port，确认 netstat |
| 采集有数据但 JetLinks 不显示 | 物模型属性 ID 或类型不匹配 | 平台物模型 temperature/humidity 选 double |
| `[modbus] socket connect 超时` | 防火墙拦截或 IP 冲突 | PC 防火墙放行 Python，ping ESP32 IP |
| `[main] Modbus 网关已停止` | main.py 里 modbus_gw 导入失败 | 重传 modbus_gw.py 到板子 |
| 板子卡 REPL，按钮不响应 | 刚才用过 `mpremote exec` | reset 板子 |

## Day7 学了什么

- **单线程系统里的并发**：时间片轮询 / 协作式调度 vs 抢占式多线程
- **MicroPython 异步模型**：为什么不能在回调里做阻塞操作
- **嵌入式 Modbus TCP**：MBAP/PDU 帧结构、字节序、连接池
- **故障模式设计**：从站失败怎么办 → 冷却机制保证主业务（继电器）不受影响
- **配置化 vs 硬编码**：采集点列表从代码常量改成 JSON 配置
