# simulator · 程序说明与完整操作手册（新手友好版）

本目录包含全部设备模拟器、实物固件与辅助工具。**每个程序是什么、怎么启动、三种运行场景如何搭配**，看这一份文档即可。已按 0 基础视角撰写：每一步做什么、预期看到什么、报错了怎么办，跟着做就能跑通。

---

## 0. 开始之前：先搞懂几个词（30 秒版）

| 名词 | 一句话解释 | 在本项目里对应什么 |
|---|---|---|
| **Modbus** | 工业设备之间读写数据的通信协议 | PC / 平台 通过它读写继电器和温湿度 |
| **从站 (Slave)** | 被"读/写"的服务端设备，存着一堆数据 | 实训教室的从站设备 / 电脑上的模拟从站 / ESP32 板子 |
| **寄存器 (Register)** | 从站里的一个个"数据格子"，有编号 | reg0=温度，reg1=湿度，reg2~9=继电器1~8 |
| **MQTT** | 通过"话题(topic)"收发消息的网络协议 | 设备和平台都通过它收发消息 |
| **topic** | 消息的"地址"，像聊天频道的名字 | 如 `/relay-cc/relaycc/properties/report` |
| **EMQX** | MQTT 服务器（邮局），所有消息经它转发 | 老师提供的 `172.16.4.211:9783` |
| **JetLinks** | 物联网云平台，负责展示数据、下发控制命令 | 网页平台，看数据/点开关的地方 |
| **物模型** | 平台上定义的"设备有哪些属性" | relay1~8、temperature、humidity 等 |

本项目有**两条数据链路**，先有个整体印象：

```
链路一 (PC模拟器):  Modbus从站 ←读取─ PC模拟器 ─上报→ EMQX ─→ JetLinks平台 ←─ 网页点开关
链路二 (实物ESP32):  PC模拟器 ─读取─→ ESP32板子(它自己就是从站)，平台部分与链路一相同
```

---

## 1. 准备工作（每台电脑只需做一次）

### 1.1 安装 Python

1. 打开官网 https://www.python.org/downloads/ 下载 Python 3.10 以上版本
2. 安装时**务必勾选 "Add Python to PATH"**，然后一路下一步
3. 验证：按 `Win+R` 输入 `powershell` 回车，在黑窗口输入：
   ```powershell
   python --version
   ```
   显示 `Python 3.10.x` 之类即成功。

### 1.2 安装本项目依赖库

```powershell
cd E:\shixiproject\traeproject1
pip install -r simulator\day1\requirements.txt -r simulator\day2\requirements.txt
```

验证：`pip show pymodbus` 能显示版本号即可。

### 1.3 安装 MQTTX（手动发消息的调试工具，类似"聊天工具"）

1. 打开 https://mqttx.app/ 下载 Windows 版并安装
2. 老师服务器的连接信息（后面会反复用到，建议记下来）：

| 项目 | 值 |
|---|---|
| Broker 地址 | `172.16.4.211` |
| 端口 | `9783`（协议选 **TCP**，不要选 ws/wss） |
| 用户名 / 密码 | `test` / `123456` |

### 1.4 实物测试额外需要（只有场景三需要）

- ESP32 板 + USB 数据线（供电 + 烧录两用）
- `pip install esptool mpremote pyserial`（烧录和上传工具）

---

## 2. 程序对照表（每个文件是干什么的）

### day1/ — 温湿度传感器（原始报文版，阶段 1）

| 文件 | 说明 |
|---|---|
| `sensor_simulator.py` | 温湿度传感器模拟器：5 秒轮询 Modbus → 变化才上报原始报文到 `device/sensor/sevengroup`（需配合 EMQX 规则引擎转换后才能进 JetLinks） |
| `config.json` | Modbus 地址、MQTT broker、上报主题等配置 |
| `requirements.txt` | day1 依赖（pymodbus 3.6.9 / paho-mqtt 1.6.1） |

### day2/ — JetLinks 直连版模拟器 + Web 控制台（阶段 2，日常主要用这个）

| 文件 | 说明 |
|---|---|
| `sensor_simulator_jl.py` | 温湿度传感器模拟器（JetLinks 官方协议直连，上报 `temperature`/`humidity`，支持设温湿度等功能调用） |
| `relay_simulator_jl.py` | **8 路继电器模拟器**（JetLinks 直连，是"平台 ↔ Modbus 从站"的桥梁：读 reg2~9 → 上报 relay1~8；收到控制命令 → 写寄存器 → 回复平台 → 上报新状态） |
| `relay_ui.py` | **继电器 Web 控制台**：浏览器打开 http://127.0.0.1:8081 即可点开关。两种模式：<br>• **MQTT 链路模式**：走"平台→EMQX→模拟器→从站"完整链路（推荐，能看到真实报文日志）<br>• **直连 Modbus 模式**：直接读写从站寄存器，不经过平台（调试从站/实物时用） |
| `config_relay.json` | 继电器模拟器/UI 的配置（从站地址、MQTT、产品/设备 ID） |
| `config_jetlinks.json` | 温湿度模拟器配置 |
| `start_relay.bat` / `start_sensor.bat` / `start_ui.bat` | **Windows 一键启动脚本，双击即可**，不用记命令 |
| `emqx_rule.sql` | 方式一（EMQX 规则引擎）的 SQL 与动作配置说明 |
| `test_format_compare.py` | 两种上报格式对比测试 |
| `requirements.txt` | day2 依赖（含 flask 3.0.3） |

### esp32/ — 实物测试固件（阶段 3，ESP32-C3 四路继电器板）

| 文件 | 说明 |
|---|---|
| `boot.py` | 上电自动连 WiFi |
| `config.py` | 全局配置：WiFi 账号、MQTT、继电器 GPIO、触发电平 |
| `relay_hw.py` | GPIO 抽象层（逻辑 0/1 ↔ 电平换算），**上电默认 4 路全开** |
| `main_mqtt.py` | **路线 A**：板子作为 MQTT 设备直连 EMQX，脱离 PC 独立上报/受控 |
| `main_modbus.py` | **路线 B**：板子作为 Modbus TCP 从站（端口 502），PC 端直接读写控制继电器 |
| `serial_monitor.py` | 串口日志工具（看板子打印了什么、IP 是多少） |
| `umqtt/simple.py` | MicroPython 官方 MQTT 库 |
| `_firmware/ESP32_GENERIC_C3-v1.29.0.bin` | MicroPython 固件（烧录一次即可） |

### tools/ — 辅助工具

| 文件 | 说明 |
|---|---|
| `modbus_slave_sim.py` | 本地 Modbus 从站模拟器（模拟实训从站）。**本地测试时必须第一个启动** |
| `modbus_scan.py` | 从站寄存器扫描工具（排查"读寄存器报错"） |
| `diag_*.py` | MQTT/平台链路诊断脚本（排查"平台没数据"时用） |
| `start_slave.bat` | 一键启动本地从站 |

---

## 3. 场景一：本地自测（不依赖老师服务器，验证程序逻辑）

> 适合：在家/没网/想先确认程序本身没问题。

**第 1 步：启动本地从站（必须第一个启动）**

双击 `tools\start_slave.bat`，或在 PowerShell 里：

```powershell
cd E:\shixiproject\traeproject1
python tools\modbus_slave_sim.py
```

✅ 预期：窗口显示从站在 `127.0.0.1:5502` 监听，后续继电器操作会有 🔔 日志。

**第 2 步：确认两个配置指向本地**

用记事本/IDE 打开检查：
- `day2\config_relay.json` → `"modbus"` 里 `"host": "127.0.0.1"`，`"port": 5502`
- `day2\config_jetlinks.json` → 同样指向 `127.0.0.1:5502`

**第 3 步：启动两个模拟器**

双击 `day2\start_relay.bat` 和 `day2\start_sensor.bat`。

✅ 预期：继电器窗口显示"MQTT 已连接"和订阅的 topic；MQTT 连不上服务器不影响 Modbus 部分测试。

**第 4 步（可选）：用 Web 控制台点一下**

双击 `day2\start_ui.bat` → 浏览器打开 http://127.0.0.1:8081 → 切到"直连 Modbus 模式" → 点 relay1。

✅ 预期：第 1 步的从站窗口出现 🔔 继电器1 操作记录。

---

## 4. 场景二：完整平台链路（实验室标准玩法，数据进 JetLinks）

> 适合：在实验室，想让数据上 JetLinks 平台、网页远程控制。
> 前提：配置指向实验室环境 —— `config_relay.json` 的 `"modbus.host": "192.168.20.59"`、`"port": 5502`（实训从站），MQTT 为 `172.16.4.211:9783`。

**第 1 步：启动模拟器**

双击 `day2\start_relay.bat` 和 `day2\start_sensor.bat`。

✅ 预期：终端显示"MQTT 已连接"。若显示连接失败，检查实验室网络能否通 `172.16.4.211`（`ping 172.16.4.211`）。

**第 2 步：在 JetLinks 平台查看数据**

浏览器登录 JetLinks 平台 → 左侧"设备管理" → 找到设备 `relaycc`（继电器）和 `sensorcc`（温湿度）→ "运行状态"页签看属性值。

✅ 预期：relay1~8 有值；温湿度有数值。**注意：模拟器只在数值变化时上报**，安静的终端是正常的。

**第 3 步：远程控制（三种方式任选）**

- 方式 A · 平台网页：设备详情 → 编辑属性 relay1=1 → 保存，即可远程开关
- 方式 B · Web 控制台：双击 `start_ui.bat` → http://127.0.0.1:8081 → **MQTT 链路模式** → 点开关，右侧能看到完整报文日志
- 方式 C · MQTTX 手动发命令 → 见下面第 5 节

**⚠️ 平台显示"在线"但收不到数据？** 这是最常见的坑（僵死会话）：设备详情页点右上角「断开连接」，然后重启模拟器，即可恢复。

---

## 5. MQTTX 手动控制指令（调试利器）

### 5.1 新建连接（第一次用照着点）

1. 打开 MQTTX → 点左侧 **`+ New Connection`**
2. 按下表填写：

| 字段 | 填什么 |
|---|---|
| Name | 随意，如 `jqd-tcp` |
| Client ID | 如 `mqttx-cc`（**不能**和模拟器的 client_id 重复，否则互踢下线） |
| Host | `mqtt://` 协议 + `172.16.4.211` |
| Port | `9783` |
| Username / Password | `test` / `123456` |

3. 点右上角 **Connect**，顶栏变绿即连接成功。

### 5.2 发送控制命令

1. 连接页**下方的消息输入区**：格式选 `JSON`
2. Topic 栏填（注意开头有个 `/`）：

```
/relay-cc/relaycc/function/invoke
```

3. Payload 栏填：

```json
{"messageId":"mqttx-all-on","functionId":"all_on","inputs":[]}
```

4. 点右侧绿色 **发送**（纸飞机按钮）。上方对话区出现绿色气泡 = 发送成功。

5. **全灭**只需把 `all_on` 改成 `all_off`（messageId 也随手改一下，如 `mqttx-all-off`）。

### 5.3 订阅验证（看设备的回话）

点 **`+ New Subscription`** → Topic 填 `/relay-cc/relaycc/properties/report` → 确认。命令执行成功后，这里会收到设备的最新状态（白色气泡）。

### 5.4 常用命令速查表

| 想做什么 | Topic | Payload |
|---|---|---|
| 继电器全开 | `/relay-cc/relaycc/function/invoke` | `{"messageId":"a1","functionId":"all_on","inputs":[]}` |
| 继电器全关 | `/relay-cc/relaycc/function/invoke` | `{"messageId":"a2","functionId":"all_off","inputs":[]}` |
| 单路控制（开 relay3） | `/relay-cc/relaycc/properties/write` | `{"messageId":"w3","properties":{"relay3":1}}` |
| 温湿度同时设值 | `/sensor-cc/sensorcc/function/invoke` | `{"messageId":"s1","functionId":"set_both","inputs":[{"name":"temperature","value":25},{"name":"humidity","value":60}]}` |
| 只设温度 | `/sensor-cc/sensorcc/function/invoke` | `{"messageId":"s2","functionId":"set_temperature","inputs":[{"name":"value","value":30}]}` |

**⚠️ 新手最容易踩的坑**：
- topic 开头的 `/` 不能少；设备名不能错——`relay-cc/relaycc` 是继电器，`sensor-cc/sensorcc` 是温湿度，发错设备没反应
- 不要发到 `/reply` 结尾的主题——那是设备**回复**平台用的通道，设备不会监听它
- `messageId` 随便填但别重复；QoS 保持 0 或 1 都行；**Retain 不要勾**
- 发命令前确认 `relay_simulator_jl.py` 在运行（实物路线 A 则是板子在线）

---

## 6. 场景三：实物测试（ESP32 四路继电器板）

> 板子：ESP32-C3 四路继电器开发板。USB 线连接电脑 = 供电 + 烧录 + 看日志。
> 板子行为：上电自动连 WiFi，**4 路继电器默认全开**（程序设计如此）。

### 6.1 第一次烧录（只需做一次）

```powershell
cd E:\shixiproject\traeproject1\simulator\esp32

:: 1. 擦除并烧录 MicroPython 固件（COM5 按实际端口改，见下方说明）
python -m esptool --port COM5 erase_flash
python -m esptool --port COM5 write_flash 0x0 _firmware\ESP32_GENERIC_C3-v1.29.0.bin

:: 2. 上传公共代码（两条路线都要传）
python -m mpremote cp config.py relay_hw.py boot.py umqtt/simple.py :/
```

> **COM 口怎么看**：板子插上 USB → `Win+X` → 设备管理器 → "端口(COM 和 LPT)" → 看新增的 `USB Serial Device (COMx)`，x 就是你的端口号。
> **预期输出**：烧录时进度条到 100%；上传时显示传输文件名。

### 6.2 选择路线（本质 = 决定板子上的 main.py 是谁）

板子上电后自动运行名为 `main.py` 的文件。**把哪个固件复制成 main.py，就走哪条路线**：

**路线 B（推荐先测）：板子 = 从站，PC 无缝替换"实训从站"**

```powershell
:: 1. 把路线B固件设为 main.py 并重启板子
python -m mpremote cp main_modbus.py :/main.py
python -m mpremote reset

:: 2. 看板子打印的 IP（重点！WiFi 分配的 IP 可能变化）
python serial_monitor.py COM5 15
```

✅ 预期串口输出：
```
boot: WiFi OK, IP = 192.168.30.145
[modbus] Modbus TCP 从站已启动 192.168.30.145:502  unit_id=7
```

```powershell
:: 3. PC 端 config_relay.json 的 modbus 改为板子的 IP:
::    "host": "192.168.30.145", "port": 502  (unit_id 保持 7)
:: 4. 双击 day2\start_ui.bat -> 页面右上角切到「直连 Modbus 模式」
```

✅ 预期：网页右上角"从站已连接"变绿；点继电器 1~4 → **板子对应继电器咔哒吸合/断开、指示灯亮灭**。

**路线 A：板子 = MQTT 设备，脱离 PC 独立上报平台**

```powershell
python -m mpremote cp main_mqtt.py :/main.py
python -m mpremote reset
```

> **⚠️ 必须先关闭 PC 端 `relay_simulator_jl.py`**：板子和 PC 模拟器用的是同一个平台设备（relaycc），同时上报会互相顶掉会话，平台数据就乱了。

✅ 预期：JetLinks 平台 `relaycc` 设备属性 relay1~4 正常显示（上电全为 1），平台编辑属性即可远程控制实物。

### 6.3 看板子日志 / 改完代码重新上传

```powershell
python serial_monitor.py COM5 25        :: 复位板子并打印 25 秒启动日志
python -m mpremote cp relay_hw.py :/    :: 只更新某个文件
python -m mpremote reset                :: 让板子重启生效
```

---

## 7. 配置速查

| 运行环境 | Modbus 从站地址 | port | unit_id | 从站是谁 |
|---|---|---|---|---|
| 本地自测 | 127.0.0.1 | 5502 | 7 | `tools/modbus_slave_sim.py` |
| 实验室实训从站 | 192.168.20.59 | 5502 | 7 | 实训教室设备 |
| ESP32 实物（路线B） | 以串口打印的 IP 为准 | 502 | 7 | 板子本身 |

- MQTT 一律 `172.16.4.211:9783`（test/123456）
- 继电器板为**高电平触发**（`config.py` 的 `RELAY_ACTIVE_LOW = False`）；换板后若"UI开=灭/关=亮"，改这个开关
- 寄存器：reg0=温度×10，reg1=湿度×10，reg2~9=继电器1~8（0=关 1=开）

## 8. 常见问题排查（按现象查）

| 现象 | 原因与处理 |
|---|---|
| 平台显示在线但收不到新数据 | 僵死会话。设备详情页点「断开连接」→ 重启模拟器 |
| 模拟器连从站报 IllegalAddress | 寄存器越界。检查 `register_start=2 / register_count=8`；用 `modbus_scan.py` 扫描确认 |
| 继电器模拟器连实物 `Connection timed out` 反复重试 | ① `ping 板子IP` 看通不通；② 通但连不上 = 板子上从站程序没在跑，`python serial_monitor.py COM5 15` 看日志并复位；③ 模拟器每 5 秒自动重试，从站恢复后会自动连上，无需重启 |
| MQTTX 发命令没反应 | 90% 是 topic 发错：必须发到 `/relay-cc/relaycc/function/invoke`（见 5.4 速查表）；发到 sensorcc 或 `/reply` 结尾的主题无效 |
| 控制无反应（MQTT 模式） | 确认 `relay_simulator_jl.py` 在跑；确认没有第二个相同程序的窗口（client_id 冲突互踢） |
| 值莫名自己变 | 实训从站是共享的，可能被其他小组写入；本地复现用 `modbus_slave_sim.py` |
| 实物"UI开=灭/关=亮" | 触发电平配反，`config.py` 改 `RELAY_ACTIVE_LOW` 后重新 `mpremote cp config.py :/` + reset |
| 任务管理器杀进程误伤 | 不要 `taskkill /IM python.exe`（会把从站一起杀掉）；直接关对应窗口 |
