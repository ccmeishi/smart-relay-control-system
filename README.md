# 智能继电器控制系统

> Day1 ~ Day7 演进记录 | ESP32-C3 + MicroPython + Modbus + MQTT + JetLinks

---

## 一、项目在干什么

想象一个智能大棚场景：

```
大棚里: 温度传感器、湿度传感器、4 个通风/浇水继电器
    ↓ RS485 串口或以太网 ↓
Modbus 从站（传感器盒子）
    ↓ WiFi ↓
ESP32-C3 开发板（网关）
    ↓ MQTT ↓
JetLinks 物联网平台（云服务器 172.16.4.211）
    ↓ 浏览器/App ↓
你坐在电脑前看数据、点按钮控制继电器
```

ESP32 固件是中间那台"网关"，它干 3 件事：
1. **往下**：通过 Modbus TCP 读传感器寄存器、写继电器开关
2. **往上**：通过 MQTT 把数据上报 JetLinks、接收控制指令
3. **自己**：管理 4 路继电器 GPIO、处理按键、断线重连

### 接线（ESP32-C3 四路继电器开发板）

| 继电器 | GPIO | 说明 |
|--------|------|------|
| 继电器 1 | GPIO 3 | 高电平触发 |
| 继电器 2 | GPIO 4 | 高电平触发 |
| 继电器 3 | GPIO 5 | 高电平触发 |
| 继电器 4 | GPIO 7 | 高电平触发 |

| 按键 | GPIO | 功能 |
|------|------|------|
| SW1 | GPIO 10 | 短按切继电器1，**长按6秒进配网模式** |
| SW2 | GPIO 9 | 短按切继电器2，双击切全部开关 |
| SW3 | GPIO 6 | 短按切继电器3 |
| SW4 | GPIO 8 | 短按切继电器4 |

---

## 二、Day1 ~ Day7 演进

| 天 | 主题 | 新增能力 | 关键文件 |
|----|------|---------|---------|
| Day1 | PC 端温湿度模拟器 | Modbus 从站模拟器，温湿度寄存器漂移 | `modbus_slave_sim.py` |
| Day2 | PC 端继电器模拟器 | 8 路继电器模拟器，JetLinks MQTT 上报 | `relay_simulator_jl.py` |
| Day3 | 继电器 Web UI | Flask 双模式 UI（MQTT 链路 / 直连 Modbus） | `relay_ui.py` |
| Day4 | JetLinks 平台对接 | 物模型、功能定义、MQTT Broker 接入 | — |
| Day5 | ESP32 继电器固件 | MicroPython 固件 + AP 配网 + MQTT 直连 | `main.py`, `relay_hw.py`, `ap_config.py` |
| Day6 | 双模式验证 | MQTT 直连 vs Modbus+网关，两种接入路线对比 | — |
| **Day7** | **Modbus 采集网关** | **时间片轮询、多从站、独立采集周期、scale 缩放** | **`modbus_gw.py`** |

---

## 三、ESP32 固件文件地图

```
simulator/esp32/
├── boot.py              ← 最先跑，连 WiFi
├── main.py              ← 主入口 + mqtt_loop + 所有功能整合
├── app_config.py        ← config.json 读写 + 默认值 + 原子写
├── ap_config.py         ← AP 热点 + HTTP 配网页（含 Modbus 配置卡片）
├── relay_hw.py          ← GPIO 控制 + 按键扫描（Timer 定时）
├── modbus_gw.py         ← ⭐ Day7 新增：Modbus TCP 主站 + 时间片调度
├── config.py            ← 早期硬编码配置（已被 app_config 替代）
├── serial_monitor.py    ← 串口监控辅助脚本
├── umqtt/simple.py      ← MicroPython MQTT 库
└── _firmware/
    └── ESP32_GENERIC_C3-v1.29.0.bin
```

### 文件依赖关系

```
boot.py → main.py → app_config.py (读配置)
                   → relay_hw.py (GPIO+按键)
                   → modbus_gw.py (Modbus 采集)
                   → ap_config.py (配网模式)
```

---

## 四、固件烧录

### 4.1 环境准备

```powershell
pip install esptool mpremote pyserial
```

### 4.2 擦除旧固件

```powershell
python -m esptool --port COM5 erase_flash
```

### 4.3 烧录 MicroPython 解释器

```powershell
python -m esptool --port COM5 --chip esp32c3 flash_mode dio --flash_freq 40m flash_id simulator/esp32/_firmware/ESP32_GENERIC_C3-v1.29.0.bin
```

烧录完成后板子会自动重启。

### 4.4 上传固件源码

```powershell
cd simulator/esp32
python -m mpremote connect COM5 cp boot.py :/boot.py
python -m mpremote connect COM5 cp app_config.py :/app_config.py
python -m mpremote connect COM5 cp relay_hw.py :/relay_hw.py
python -m mpremote connect COM5 cp ap_config.py :/ap_config.py
python -m mpremote connect COM5 cp modbus_gw.py :/modbus_gw.py
python -m mpremote connect COM5 cp main.py :/main.py
# umqtt 库（如果板子上没有）
python -m mpremote connect COM5 mkdir umqtt
python -m mpremote connect COM5 cp umqtt/simple.py :umqtt/simple.py
```

### 4.5 验证启动

```powershell
python -c "import serial,time; s=serial.Serial('COM5',115200,timeout=1); time.sleep(3); print(s.read(s.in_waiting or 4096).decode('utf-8','replace'))"
```

预期看到：
```
boot: ESP32 启动, MAC = 7ce8b1c1a798
[main] 设备启动, MAC = 7ce8b1c1a798
[main] 连接WiFi: Office-WiFi
[main] WiFi OK, IP: 192.168.30.145
[main] MQTT 已连接 172.16.4.211:9783 设备=relaycc
[main] Modbus 网关已启动, 采集点: 3
```

---

## 五、配网流程（固件首次使用）

### 5.1 进入配网模式

两种方式：

| 方式 | 操作 | 场景 |
|------|------|------|
| 自动进入 | 板子 `/config.json` 不存在或 `is_ready()` 返回 False | 首次开机 / 手动清空配置后 |
| SW1 长按 | **长按 SW1 约 6 秒**松开 | 正常运行时想改配置 |

串口日志确认：
```
[relay_hw] SW1 长按5秒: 请求进入配网模式
[main] 收到配网请求, 切换到配网模式
[ap] 热点已开放: RELAY-SETUP-a799 (开放网络)
[ap] 手机连热点后打开 http://192.168.4.1
```

### 5.2 手机配网

1. 手机 WiFi 列表找 **`RELAY-SETUP-xxxx`**（开放网络，无密码）
2. 浏览器打开 **http://192.168.4.1**
3. 填写配置：

| 卡片 | 字段 | 示例 |
|------|------|------|
| 📶 WiFi | WiFi 名称 | `Office-WiFi` |
| | WiFi 密码 | `yh82922868` |
| ☁️ MQTT | MQTT 服务器 IP | `172.16.4.211` |
| | 端口 | `9783` |
| | 账号 | `test` |
| | 密码 | `123456` |
| | 产品 ID | `relay-cc` |
| | 设备 ID | `relaycc`（默认填 MAC 后 4 位） |
| 🔗 Modbus | 启用 | ☐ 勾选 |
| | 采集配置 JSON | 见下节 |

4. 点 **"保存并重启"**，板子自动重启进正常模式

### 5.3 Modbus 采集配置 JSON 示例

```json
[
  {
    "name": "温湿度传感器",
    "host": "192.168.30.100",
    "port": 502,
    "unit_id": 1,
    "points": [
      {"addr": "0x0000", "key": "temperature", "period_ms": 3000,
       "count": 1, "type": "uint16", "scale": 0.1},
      {"addr": "0x0001", "key": "humidity",    "period_ms": 5000,
       "count": 1, "type": "uint16", "scale": 0.1}
    ]
  },
  {
    "name": "电压电表",
    "host": "192.168.30.101",
    "port": 502,
    "unit_id": 2,
    "points": [
      {"addr": "0x0000", "key": "voltage", "period_ms": 10000,
       "count": 2, "type": "float_be"}
    ]
  }
]
```

### 5.4 配置字段速查

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `name` | string | 否 | 从站标识（仅日志用） |
| `host` | string | ✅ | Modbus TCP 从站 IP |
| `port` | int | ✅ | Modbus TCP 端口，默认 502 |
| `unit_id` | int | ✅ | 从站地址 1~247 |
| `addr` | string/int | ✅ | 寄存器地址，支持 `0x0000` 或十进制 |
| `key` | string | ✅ | 采集值对应的 JSON 属性名（JetLinks 物模型要配同名） |
| `period_ms` | int | ✅ | **每个点独立**的采集周期（毫秒） |
| `count` | int | 否 | 连续读取的寄存器数量，默认 1 |
| `type` | string | 否 | 数据类型，默认 `uint16` |
| `scale` | float | 否 | 缩放系数，如 `0.1` 表示原始值 × 0.1 |

### 5.5 type 可选值

| type | 占寄存器数 | 范围 | 说明 |
|------|-----------|------|------|
| `uint16` | 1 | 0~65535 | 无符号整数 |
| `int16` | 1 | -32768~32767 | 有符号整数 |
| `uint32` | 2 | 0~4294967295 | 大整数 |
| `int32` | 2 | ±2^31 | 有符号大整数 |
| `float_be` | 2 | ±3.4×10³⁸ | IEEE 754 大端浮点 |

### 5.6 存储格式与 JetLinks 显示

传感器寄存器常以 ×10 存储（266 = 26.6°C）。两种处理方式：

| 方式 | 操作 | JetLinks 显示 |
|------|------|--------------|
| **固件端 scale** | 配置 `"scale": 0.1`，固件上报 26.6 | 物模型属性类型选 `double` → 显示 26.6 |
| **JetLinks 侧值转换** | 固件原样上报 266，平台脚本 `value / 10.0` | 显示 26.6 |

培训版 JetLinks 无值转换功能，推荐固件端 scale。

---

## 六、JetLinks 平台配置

### 6.1 连接信息

| 项 | 值 |
|----|-----|
| JetLinks 地址 | http://172.16.4.211 |
| MQTT Broker | EMQX 172.16.4.211:9783 |
| MQTT 账号 | test |
| MQTT 密码 | 123456 |

### 6.2 设备接入网关

运维管理 → 设备接入网关 → MQTT Broker 接入

| 项 | 值 |
|----|-----|
| Broker 地址 | 172.16.4.211 |
| 端口 | 9783 |
| 用户名 | test |
| 密码 | 123456 |

### 6.3 产品物模型

产品管理 → 新建产品 → `relay-cc` → 物模型

| 属性 ID | 名称 | 数据类型 | 读写 | 说明 |
|---------|------|---------|------|------|
| `relay1` | 继电器1 | int(整数型) | 读写 | 0=关 1=开 |
| `relay2` | 继电器2 | int(整数型) | 读写 | |
| `relay3` | 继电器3 | int(整数型) | 读写 | |
| `relay4` | 继电器4 | int(整数型) | 读写 | |
| `temperature` | 温度 | double(双精度浮点) | 读 | 需配 `"scale": 0.1` |
| `humidity` | 湿度 | double(双精度浮点) | 读 | 需配 `"scale": 0.1` |

⚠️ **属性 ID 必须和固件上报的 key 完全一致**，否则平台静默丢弃该字段。

### 6.4 功能定义

| 功能 ID | 名称 | 输入参数 | 说明 |
|---------|------|---------|------|
| `set_relay` | 设置单个继电器 | 继电器编号(int), 状态(int) | 继电器编号 1~4，状态 0/1 |
| `all_on` | 全部打开 | 无 | |
| `all_off` | 全部关闭 | 无 | |
| `toggle_relay` | 切换继电器 | 继电器编号(int) | |
| `batch_set` | 批量设置 | 继电器数组, 状态数组 | |

### 6.5 设备下发指令格式

JetLinks 3.x 通过 MQTT 下发，设备需订阅这些 Topic：

| Topic | 方向 | 说明 |
|-------|------|------|
| `/{productId}/{deviceId}/properties/report` | 设备→平台 | 属性上报 |
| `/{productId}/{deviceId}/properties/write` | 平台→设备 | 属性写入指令 |
| `/{productId}/{deviceId}/function/invoke` | 平台→设备 | 功能调用 |
| `/{productId}/{deviceId}/function/invoke/reply` | 设备→平台 | 功能调用回复 |

**功能调用示例**（MQTTX 手动测试）：

```
Topic:  /relay-cc/relaycc/function/invoke
Payload: {"messageId":"t1","functionId":"set_relay","inputs":{"继电器编号":1,"状态":0}}
```

或用英文参数名：
```json
{"messageId":"t1","functionId":"set_relay","inputs":{"relay":1,"state":0}}
```

或数组格式（JetLinks 自动生成的）：
```json
{"messageId":"t1","functionId":"set_relay","inputs":[{"name":"继电器编号","value":1},{"name":"状态","value":0}]}
```

### 6.6 回复格式

设备收到指令后必须回复 invoke/reply：
```json
{"messageId":"t1","success":"success"}
```

同时立即发 properties/report 更新状态：
```json
{"timestamp":1725678901234,"messageId":"esp32-xxx","properties":{"relay1":0,"relay2":1}}
```

---

## 七、PC 端工具

### 7.1 Modbus TCP 从站模拟器

用于本地测试 Modbus 采集功能：

```powershell
cd simulator/tools
python modbus_slave_sim.py 5502 7
```

| 参数 | 说明 |
|------|------|
| 5502 | 监听端口 |
| 7 | 从站地址 (unit_id) |

模拟器寄存器布局：

| 寄存器 | 名称 | 格式 | 初始值 |
|--------|------|------|--------|
| reg0 | 温度 | ×10, uint16 | 253 (25.3°C) |
| reg1 | 湿度 | ×10, uint16 | 567 (56.7%RH) |
| reg2~9 | 继电器1~8 | uint16, 0/1 | 0 |
| reg10 | 总电流 | ×10, uint16 | 0.0A |
| reg11 | 电压 | ×10, uint16 | 220.0V |

温湿度每 2 秒随机漂移一次。

### 7.2 继电器 UI

```powershell
cd simulator/day2
python relay_ui.py
```

浏览器打开 http://localhost:8081

两种模式：
- **MQTT 链路模式**：通过 EMQX 和 JetLinks 交互
- **直连 Modbus 模式**：PC 直接通过 Modbus TCP 控制从站

### 7.3 MQTTX 客户端

用于查看 MQTT 消息、手动下发指令：

| 项 | 值 |
|----|-----|
| Host | 172.16.4.211 |
| Port | 9783 |
| Username | test |
| Password | 123456 |

订阅 `relaycc/#` 可看到板子所有收发消息。

---

## 八、Day7 核心设计详解

### 8.1 为什么不能用多线程

MicroPython 的 GIL（全局解释器锁）同一时刻只允许一个线程执行 Python 字节码。多线程并不能真正并行，还会导致 socket 操作冲突。**正确做法是时间片轮询 + 非阻塞设计**。

### 8.2 时间片轮询调度器

```python
# main.py 主循环
while True:
    relay_hw.check_keys()    # 扫描按键（Timer 回调）
    _cli.check_msg()         # 处理 MQTT 下行（非阻塞）
    modbus_gw.poll_one()     # ⭐ 只采 1 个 Modbus 点
    _maybe_ping()            # 定时发 ping
    _maybe_report()          # 变化检测 → 上报
```

`poll_one()` 每次只执行一个采集点，读完立即返回。多个到期点按**配置顺序**依次执行，不会并发冲突。

### 8.3 冷却防阻塞

从站连续失败 3 次后进入 30 秒冷却，期间所有对该从站的请求**直接跳过**，不发起任何 socket 操作，主循环零阻塞。成功连接后重置冷却。

### 8.4 Modbus TCP 帧结构

```
MBAP 头 (7 字节)          PDU 载荷
┌─────────────────────┐ ┌──────────────────┐
│ 事务ID(2)│协议ID(2)  │ │功能码(1)+数据     │
│ 长度(2)  │从站ID(1) │ │                   │
└─────────────────────┘ └──────────────────┘
```

全部大端字节序，由 `struct.pack(">HHHB", ...)` 打包。

### 8.5 MQTT 上报合并

```python
def properties():
    props = dict(relay_hw.states())       # {'relay1':1, 'relay2':0}
    props.update(modbus_gw.collected())   # {'temperature':26.6}
    return props                           # {'relay1':1, 'relay2':0, 'temperature':26.6}
```

继电器状态和 Modbus 数据**一条消息**上报，JetLinks 物模型属性 ID 和配置 key 一一对应。

---

## 九、常见问题排查

### 9.1 板子串口无输出

| 可能 | 解决 |
|------|------|
| mpremote 卡在 REPL 模式 | 重新烧录固件或按复位键 |
| 串口端口被占用 | 关掉其他串口监控程序 |
| 波特率不对 | 必须是 115200 |

### 9.2 WiFi 连不上

| 可能 | 解决 |
|------|------|
| 密码错 | 长按 SW1 重配网 |
| 信号弱 | 换近点或用手机热点 |
| 路由器限制 | 检查 MAC 地址过滤 |

### 9.3 MQTT 连接不上

| 可能 | 解决 |
|------|------|
| JetLinks 设备会话僵死 | 平台设备详情点"断开连接"→ 重启板子 |
| client_id 冲突 | 确保只有一个板子/模拟器用 relaycc |
| EMQX unretain 脏数据 | 代码已 publish("", retain=True) 清除 |

### 9.4 Modbus 采集失败

| 日志 | 原因 | 解决 |
|------|------|------|
| `ETIMEDOUT` | 从站不可达 | 防火墙放行、模拟器是否启动 |
| `ECONNRESET` | 连接被从站拒绝 | 从站地址/端口是否正确 |
| 进入 30 秒冷却 | 连续失败 3 次 | 等冷却结束自动重试 |
| 数据值离谱 | 从站寄存器格式 | 检查 type 和 scale 配置 |

### 9.5 继电器控制无反应

| 可能 | 解决 |
|------|------|
| SW1 长按进配网失效 | 板子需在正常运行模式（不是 AP 模式） |
| MQTT 指令超时 | JetLinks 会话僵死 → 断开重连 |
| 继电器硬件电平 | 确认是高电平触发 |

### 9.6 JetLinks 平台显示"有连接没数据"

| 可能 | 解决 |
|------|------|
| 属性 ID 拼写错误 | 物模型属性 ID 必须和固件上报 key 完全一致 |
| 数据类型不匹配 | relay1 是 int，temperature 带 scale 后是 double |
| 设备会话僵死 | 断开连接 → 重启板子 |

### 9.7 配网页面打不开

| 可能 | 解决 |
|------|------|
| 手机用 4G 上网 | 关掉蜂窝数据，只走 WiFi |
| 板子还在正常模式 | 长按 SW1 6 秒进配网 |
| http:// 写成 https:// | 必须 http://192.168.4.1 |

### 9.8 MicroPython 兼容性坑

| 问题 | 解决 |
|------|------|
| `json.dumps(ensure_ascii=False)` 报错 | 去掉这个参数，MicroPython 默认不转义 |
| socket timeout 不能异步 | 时间片轮询 + 冷却机制 |
| 无完整标准库 | 手写 HTTP 服务器用 socket |
| 文件写入非原子 | 先写 .tmp 再 os.rename() |

---

## 十、快速验证清单

### Day7 验收测试

| # | 测试项 | 通过标志 |
|---|--------|---------|
| 1 | 板子启动 | WiFi OK + MQTT 已连 + Modbus 网关已启动 |
| 2 | 本地按键控制 | SW1~SW4 短按切换继电器，日志 + 灯都有 |
| 3 | JetLinks set_relay | 继电器编号=1,状态=0 → 灯灭 + 日志回复 |
| 4 | JetLinks all_on/all_off | 全开全关，4 路灯同步变化 |
| 5 | Modbus 采集 | 模拟器启动后日志出现 `[modbus] temperature = 26.6` |
| 6 | 数据上报合并 | 上报 payload 同时包含 relay1~4 和 temperature/humidity |
| 7 | 非阻塞 | 采集持续运行时按键和 MQTT 指令无延迟 |
| 8 | scale 生效 | 串口日志里 temperature 是 26.6 不是 266 |
| 9 | 冷却机制 | 关闭模拟器，日志出现"进入 30 秒冷却"且不再阻塞 |
| 10 | 配网改配置 | AP 模式改 Modbus JSON → 重启生效 |

---

## 附录：MQTT 消息格式速查

### 上报（设备 → 平台）

```
Topic: /relay-cc/relaycc/properties/report
```

```json
{
  "timestamp": 1725678901234,
  "messageId": "esp32-7ce8b1c1a798-1725678901",
  "properties": {
    "relay1": 1,
    "relay2": 0,
    "relay3": 1,
    "relay4": 1,
    "temperature": 26.6,
    "humidity": 75.1
  }
}
```

### 功能调用（平台 → 设备）

```
Topic: /relay-cc/relaycc/function/invoke
```

```json
{
  "messageId": "t1",
  "functionId": "set_relay",
  "inputs": {"继电器编号": 1, "状态": 0}
}
```

### 功能回复（设备 → 平台）

```
Topic: /relay-cc/relaycc/function/invoke/reply
```

```json
{"messageId": "t1", "success": "success"}
```

### 属性写入（平台 → 设备）

```
Topic: /relay-cc/relaycc/properties/write
```

```json
{"messageId": "t2", "properties": {"relay1": 0}}
```

### 属性读取（平台 → 设备）

```
Topic: /relay-cc/relaycc/properties/read
```

```json
{"messageId": "t3", "properties": ["relay1", "relay2"]}
```
