# 智能继电器控制系统

> Day1 ~ Day8 完整记录 | ESP32-C3 + MicroPython + Modbus + MQTT + Python Bridge + JetLinks

---

## 一、项目在干什么

想象一个智能家居/智慧大棚场景：

一块 ESP32-C3 四路继电器开发板当**网关**，它一边用 GPIO 控制 4 路继电器，一边用 Modbus TCP 读外部传感器（温湿度、人体感应、烟雾），然后把所有数据通过 MQTT 上报。**一台物理网关，在 JetLinks 平台上"分身"成 6 个不同的虚拟产品**（门锁、灯、空调、温湿度、人体、烟雾），由一个 Python Bridge 程序负责把网关的数据按路由表拆分转发。

```
                         ┌─────────────────────────────┐
  Modbus 从站模拟器       │      ESP32-C3 网关           │
  (温湿度/人体/烟雾)       │  (一块板子, 产品 relay-cc)    │
  192.168.20.59:5502 ────▶│  GPIO 4路继电器 + Modbus采集  │
                         └──────────────┬──────────────┘
                                        │ MQTT 上报 (所有数据混在一条消息)
                                        ▼
                         ┌─────────────────────────────┐
                         │   Python Bridge (电脑上跑)    │
                         │  按路由表拆分 + 下行回流       │
                         └──────────────┬──────────────┘
                                        │ MQTT 转发 (每个虚拟产品一条 topic)
            ┌───────────┬───────────┬───┴────────┬───────────┬──────────┐
            ▼           ▼           ▼            ▼           ▼          ▼
        门锁 lock-cc  灯 light-cc  空调 ac-cc  温湿度       人体       烟雾
        lock001       light001/2   ac001      sensor-cc   human-cc   smoke-cc
                                                sensorcc   human001   smoke001
                                        │
                                        ▼
                         JetLinks 物联网平台 (172.16.4.211)
                                        │
                                        ▼
                              浏览器看数据、点按钮控制
```

ESP32 网关固件干 3 件事：
1. **往下**：通过 Modbus TCP 读传感器寄存器（温湿度/人体/烟雾）
2. **往上**：通过 MQTT 把"继电器状态 + 传感器数据"一起上报、接收控制指令
3. **自己**：管理 4 路继电器 GPIO、处理按键、断线重连、数据飘动

Python Bridge 干 2 件事：
1. **上行拆分**：订阅网关的混在一起的数据，按路由表拆成 6 个虚拟产品分别上报
2. **下行回流**：平台对虚拟产品（比如门锁、灯）的控制指令，路由回网关对应的继电器

> 📌 **Day8 是重点**：前面 Day1~7 都是"一块板子 = 平台上一个设备"。Day8 引入 Bridge，让**一块物理板子在平台上呈现为多个不同类型的智能设备**，这是真实工业网关的典型用法。详见 [第十三章 Day8](#十三day8网关--bridge一台板子变六个设备)。

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

## 二、环境准备（一次性）

```powershell
# Python 依赖
pip install pymodbus paho-mqtt flask esptool mpremote pyserial

# MQTTX 客户端 (下载安装)
# https://mqttx.app/zh

# JetLinks 平台（老师提供）
# http://172.16.4.211  账号 admin7 / 密码见平台
```

![开发环境](开发环境.png)

### JetLinks 连接信息速查

| 项 | 值 |
|----|-----|
| JetLinks 地址 | http://172.16.4.211 |
| MQTT Broker | EMQX 172.16.4.211:9783 |
| MQTT 账号 | test |
| MQTT 密码 | 123456 |
| 产品 ID | relay-cc |
| 设备 ID | relaycc |

### MQTTX 新建连接

| 项 | 值 |
|----|-----|
| Host | 172.16.4.211 |
| Port | 9783 |
| Username | test |
| Password | 123456 |

订阅 `relaycc/#` 可看到板子所有收发消息。

---

## 三、Day1：PC 端温湿度模拟器

### 目标
在电脑上跑一个 Modbus TCP 从站模拟器，模拟一个有温湿度寄存器的传感器，验证 Modbus 协议基本通信。

![Day1 运行截图](day1.png)

### 运行指令

```powershell
cd simulator\tools
python modbus_slave_sim.py 5502 7
```

| 参数 | 说明 |
|------|------|
| 5502 | 监听端口（Modbus TCP 默认 502，5502 避免权限问题） |
| 7 | 从站地址 (unit_id) |

### 寄存器布局

> Day8 后模拟器扩展为多传感器，**从站模拟器**的完整寄存器布局如下（`simulator/tools/modbus_slave_sim.py`）。注意：这张表是从站（模拟器）侧的全部寄存器，ESP32 网关实际只采集其中一部分（见下方说明）：

| 寄存器 | 名称 | 格式 | 初始值 | 飘动方式 |
|--------|------|------|--------|---------|
| reg0 | 温度 | ×10, uint16 | 253 (25.3°C) | 每 2 秒 ±1~2 漂移 |
| reg1 | 湿度 | ×10, uint16 | 567 (56.7%RH) | 每 2 秒 ±1~3 漂移 |
| reg2~3 | 预留 | — | 0 | — |
| reg4 | **人体感应** | uint16, 0/1 | 1 | 每 10 秒随机切换 有人/无人 |
| reg5 | **烟雾等级** | uint16, 0~100 | 10 | 每 6 秒 ±2~20 波动，偶尔飙升 |
| reg6~9 | 继电器1~4 | uint16, 0/1 | 0 | 平台/按键控制 |
| reg10 | 总电流 | ×10, uint16 | 0.0A | 每开一路继电器 +0.5A |
| reg11 | 电压 | ×10, uint16 | 220.0V | 218~222V 波动 |
| reg12~15 | 预留 | — | 0 | — |

> ⚠️ **说明**：reg10（总电流）、reg11（电压）目前只在**从站模拟器内部**做联动/波动，**ESP32 网关设计暂无添加电流电压采集**（`esp32/config.json` 里只有温湿度、人体、烟雾 4 个采集点），所以平台上暂时看不到电流电压数据。

支持功能码：`0x03` 读保持寄存器、`0x06` 写单个寄存器。

> 💡 **数据为什么会"飘动"？** 真实传感器读到的值不会是死板的固定数。飘动逻辑有两层：模拟器自己会漂（上表），**ESP32 网关读到后还会再叠加一层小随机扰动**（见 [13.6](#136-esp32-端数据飘动为什么数据不是固定值)）。所以即使模拟器没更新，平台上看到的温湿度/人体/烟雾也会持续变化。

### 验证 Modbus 通信

用 Modbus Poll / QModMaster 连接 `127.0.0.1:5502`，unit_id=7，读 reg0~reg1：
- 如果读到 253 和 567 → ✅ Modbus 通信正常
- 如果超时 → 检查模拟器是否在跑、Windows 防火墙是否放行 5502

### 文件说明

| 文件 | 作用 |
|------|------|
| `simulator/tools/modbus_slave_sim.py` | Modbus TCP 从站模拟器（温湿度漂移 + 8 路继电器） |
| `simulator/day1/sensor_simulator.py` | 早期纯 Modbus 模拟器（不带 MQTT） |

---

## 四、Day2：PC 端继电器模拟器 + JetLinks 上报

### 目标
8 路继电器模拟器，**JetLinks MQTT 直连上报**，同时作为 Modbus TCP 从站——PC 端模拟整个"继电器设备"的行为。

### 运行指令

```powershell
# 方式1: 双击 start_relay.bat
# 方式2: 手动运行
cd simulator\day2
python relay_simulator_jl.py
```

### 配置文件

`simulator/day2/config_relay.json`：

```json
{
  "modbus": {
    "host": "127.0.0.1",
    "port": 5502,
    "unit_id": 7,
    "register_start": 2,
    "register_count": 8
  }
}
```

| 字段 | 说明 |
|------|------|
| host | Modbus 从站 IP（模拟器自己就是从站，写 127.0.0.1） |
| port | Modbus 端口 |
| unit_id | 从站地址 |
| register_start | 继电器对应的寄存器起始地址 |
| register_count | 继电器寄存器数量（8 路） |

### 文件说明

| 文件 | 作用 |
|------|------|
| `relay_simulator_jl.py` | 8 路继电器模拟器（JetLinks MQTT 直连 + Modbus TCP 从站） |
| `sensor_simulator_jl.py` | 温湿度传感器模拟器（JetLinks 直连） |
| `config_relay.json` | 继电器模拟器 Modbus 配置 |
| `config_jetlinks.json` | MQTT / JetLinks 连接配置 |
| `emqx_rule.sql` | EMQX 规则引擎 SQL（可选，用于旧版消息转换） |
| `test_format_compare.py` | 两种上报格式对比测试 |
| `start_relay.bat` | 双击启动继电器模拟器 |
| `start_sensor.bat` | 双击启动温湿度模拟器 |

### 验证流程

1. 启动 `modbus_slave_sim.py`（提供温湿度寄存器）
2. 启动 `relay_simulator_jl.py`（读 Modbus 继电器寄存器 + MQTT 上报）
3. JetLinks 平台设备管理找到 `relaycc` → 属性页刷新 → 应看到 relay1~8 + temperature + humidity
4. 平台下发 `set_relay` 指令 → 模拟器日志应显示收到并执行

---

## 五、Day3：继电器 Web UI

### 目标
用 Flask 做一个 Web 控制台，两种模式：MQTT 链路模式（走平台）和直连 Modbus 模式（直接读寄存器）。

![Day3 Web UI 截图](day3.png)

### 运行指令

```powershell
cd simulator\day2
python relay_ui.py
# 或双击 start_ui.bat
```

浏览器打开 **http://localhost:8081**

### 两种模式区别

| 模式 | 链路 | 适用场景 |
|------|------|---------|
| MQTT 链路 | UI → EMQX → JetLinks → 模拟器 | 看到真实消息日志 |
| 直连 Modbus | UI → Modbus TCP 5502 | 调试从站/实物时绕过平台 |

### 运行前置

- MQTT 链路模式：需要 `relay_simulator_jl.py` + EMQX 可达
- 直连模式：需要 `modbus_slave_sim.py` 在 5502 端口监听

### 文件说明

| 文件 | 作用 |
|------|------|
| `relay_ui.py` | Flask Web UI（嵌入 HTML 前端 + API 后端） |

---

## 六、Day4：JetLinks 平台对接

### 目标
完成 JetLinks 平台的配置，让 PC 端模拟器能上报数据、接收指令。

![Day4 JetLinks 平台](day4.jpg)

### 步骤 1：设备接入网关

运维管理 → 设备接入网关 → MQTT Broker 接入

| 项 | 值 |
|----|-----|
| Broker 地址 | 172.16.4.211 |
| 端口 | 9783 |
| 用户名 | test |
| 密码 | 123456 |

### 步骤 2：产品物模型

产品管理 → 新建产品 → `relay-cc` → 物模型

#### 属性定义

| 属性 ID | 名称 | 数据类型 | 读写 |
|---------|------|---------|------|
| `relay1` | 继电器1 | int(整数型) | 读写 |
| `relay2` | 继电器2 | int(整数型) | 读写 |
| `relay3` | 继电器3 | int(整数型) | 读写 |
| `relay4` | 继电器4 | int(整数型) | 读写 |
| `relay5` | 继电器5 | int(整数型) | 读写 |
| `relay6` | 继电器6 | int(整数型) | 读写 |
| `relay7` | 继电器7 | int(整数型) | 读写 |
| `relay8` | 继电器8 | int(整数型) | 读写 |
| `temperature` | 温度 | double(双精度浮点) | 读 |
| `humidity` | 湿度 | double(双精度浮点) | 读 |

⚠️ **属性 ID 必须和固件上报的 key 完全一致**，否则平台静默丢弃该字段。

#### 功能定义

| 功能 ID | 名称 | 输入参数 | 说明 |
|---------|------|---------|------|
| `set_relay` | 设置单个继电器 | 继电器编号(int), 状态(int) | 继电器编号 1~4，状态 0/1 |
| `all_on` | 全部打开 | 无 | |
| `all_off` | 全部关闭 | 无 | |
| `toggle_relay` | 切换继电器 | 继电器编号(int) | |
| `batch_set` | 批量设置 | 继电器数组, 状态数组 | |

### 步骤 3：创建设备

产品管理 → `relay-cc` → 设备 → 新增：
- 设备 ID：`relaycc`
- 设备名称：继电器CC

### JetLinks 会话僵死问题

如果设备显示"在线"但收不到新消息（最后上线时间停在旧时间点）：
1. 设备详情页点 **"断开连接"** 清除僵死会话
2. 重启模拟器/固件

---

## 七、Day5：ESP32 继电器固件（核心里程碑）

### 目标
用 MicroPython 给 ESP32-C3 开发板写完整固件，替代 PC 模拟器，实现：
- ✅ 4 路继电器 GPIO 控制
- ✅ SW1~SW4 按键扫描（Timer 定时）
- ✅ AP 配网模式（SW1 长按 6 秒触发）
- ✅ MQTT 直连 JetLinks（断线指数退避重连）
- ✅ 持久化配置（/config.json 原子写）

![Day5 ESP32 实物](day5.jpg)

### 7.1 固件烧录

#### 环境依赖

```powershell
pip install esptool mpremote pyserial
```

#### 擦除旧固件

```powershell
python -m esptool --port COM5 erase_flash
```

#### 烧录 MicroPython 解释器

```powershell
python -m esptool --port COM5 --chip esp32c3 flash_mode dio --flash_freq 40m flash_id simulator/esp32/_firmware/ESP32_GENERIC_C3-v1.29.0.bin
```

烧录完成后板子自动重启。

#### 上传固件源码

```powershell
cd simulator\esp32

# 核心文件
python -m mpremote connect COM5 cp boot.py :/boot.py
python -m mpremote connect COM5 cp app_config.py :/app_config.py
python -m mpremote connect COM5 cp relay_hw.py :/relay_hw.py
python -m mpremote connect COM5 cp ap_config.py :/ap_config.py
python -m mpremote connect COM5 cp main.py :/main.py

# umqtt 库（如果板子上没有）
python -m mpremote connect COM5 mkdir umqtt
python -m mpremote connect COM5 cp umqtt/simple.py :umqtt/simple.py
```

#### 串口日志监控

```powershell
# 方式1: 双击 start_serial.bat
# 方式2: 手动运行
python -c "import serial,time; s=serial.Serial('COM5',115200,timeout=1); time.sleep(2); print(s.read(s.in_waiting or 4096).decode('utf-8','replace')); s.close()"
```

预期看到：
```
boot: ESP32 启动, MAC = 7ce8b1c1a798
[main] 设备启动, MAC = 7ce8b1c1a798
[main] 连接WiFi: Office-WiFi
[main] WiFi OK, IP: 192.168.30.145
[main] MQTT 已连接 172.16.4.211:9783 设备=relaycc
```

### 7.2 配网流程

#### 进入配网模式

| 方式 | 操作 | 场景 |
|------|------|------|
| 自动进入 | 板子 `/config.json` 不存在或 `is_ready()` 返回 False | 首次开机 |
| SW1 长按 | **长按 SW1 约 6 秒**松开 | 正常运行时想改配置 |

串口确认：
```
[relay_hw] SW1 长按5秒: 请求进入配网模式
[main] 收到配网请求, 重启进入配网模式
rst:0xc (RTC_SW_CPU_RST)          ← 板子自动重启
BOOT v12 start
  检测到按键按下, 强制进入配网模式...
[ap] 热点已开放: RELAY-SETUP-a799 (开放网络)
[ap] 手机连热点后打开 http://192.168.4.1
```

> ⚠️ **Day8 重要改动**：长按后板子不是"当场切热点"，而是**写一个标记文件然后自动重启**，重启后在干净状态下进入配网。这是因为运行中直接把 WiFi 从联网模式切成热点模式时，MQTT/Modbus 的网络连接还开着，会导致板子挂死（热点开不出来）。详见 [11.7 配网页面打不开](#117-配网页面打不开)。

#### 进入配网模式的两种方式

| 方式 | 操作 | 说明 |
|------|------|------|
| **长按 SW1** | 正常运行时**按住 SW1 约 6 秒**松开 | 板子自动重启进配网（推荐） |
| **复位 + 按住任意键** | 按住 SW1~SW4 任意一个，再按一下板子 RST 复位键，继续按住 1~2 秒 | 上电时直接进配网，跳过联网 |

#### 手机配网

1. 手机 WiFi 找 **`RELAY-SETUP-xxxx`**（开放网络，无密码）
2. 浏览器打开 **http://192.168.4.1**（必须 http://，不能 https://）
3. 关掉手机蜂窝数据（避免 4G 抢流量）
4. 填写配置：

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

5. 点 **"保存并重启"**

#### 命令行快速改配置（不用进配网）

```powershell
python -m mpremote connect COM5 exec "
import app_config
c = app_config.load()
c['device_id'] = 'relaycc'
c['wifi_ssid'] = 'Office-WiFi'
app_config.save(c)
print('OK')
"
python -m mpremote connect COM5 reset
```

### 7.3 ESP32 固件文件逐个讲解

#### boot.py — 启动入口（最先执行）

```python
# boot.py
import time, network
from app_config import load

def main():
    cfg = load()
    if cfg and cfg.get("wifi_ssid"):
        # 正常运行: 连 WiFi
        sta = network.WLAN(network.STA_IF)
        sta.active(True)
        sta.connect(cfg["wifi_ssid"], cfg.get("wifi_pass", ""))
        # 等 main.py 接管后续

main()
```

**执行顺序**：ESP32 上电 → boot.py 自动执行 → main.py 执行（如果存在）

| 作用 | 说明 |
|------|------|
| 最先跑 | MicroPython 约定，boot.py 比 main.py 先执行 |
| 预连 WiFi | 提前启动 WiFi STA 模式，main.py 拿到配置后立即开始连接 |
| 轻量 | 不做太多事，避免启动时卡住 |

#### app_config.py — 配置持久化

```python
# app_config.py
CONFIG_PATH = "/config.json"

DEFAULTS = {
    "wifi_ssid": "",
    "wifi_pass": "",
    "mqtt_host": "172.16.4.211",
    "mqtt_port": 9783,
    "mqtt_user": "test",
    "mqtt_pass": "123456",
    "product_id": "relay-cc",
    "device_id": "",          # 空 → 自动填 MAC
    "modbus_enabled": False,  # Day7 新增
    "modbus_slaves": [],      # Day7 新增
}

REQUIRED = ("wifi_ssid", "mqtt_host", "device_id")
```

| 函数 | 作用 |
|------|------|
| `load()` | 读 config.json，不存在/损坏返回 None，存在则补全默认值 |
| `is_ready(cfg)` | 所有 REQUIRED 字段非空 → 足够进正常模式 |
| `save(cfg)` | 先写 .tmp 再 os.rename()，**原子写**防止掉电损坏 |
| `mac_address()` | 读设备 MAC，用于默认 device_id |

**原子写**：
```python
def save(cfg):
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        f.write(json.dumps(cfg))
    os.rename(tmp, CONFIG_PATH)  # 原子操作，要么全写要么全不写
```

#### relay_hw.py — GPIO 控制 + 按键扫描

```python
# relay_hw.py
RELAY_PINS = [3, 4, 5, 7]    # 4 路继电器 GPIO
BTN_PINS   = [10, 9, 6, 8]   # SW1~SW4 GPIO

RELAY_ACTIVE_LOW = False     # 实物测试: 高电平触发
```

| 函数/对象 | 作用 |
|-----------|------|
| `states()` | 返回当前 4 路继电器状态 `[1,0,1,0]` |
| `set(idx, on)` | 设置第 idx 路继电器开关（idx=0~3） |
| `config_requested()` | SW1 是否长按了 6 秒（配网模式触发器） |
| `attach_buttons()` | 启动 Timer(0)，每 50ms 扫一次按键 |
| Timer 回调 | 检测按下/松开/长按，触发回调 |

**长按判定逻辑**：
```
按键按下 → start_time 记录
持续按住 → 每秒检查是否够 6 秒
够了 → config_request = True → 主循环检测到后切配网模式
松开 → 重置 start_time
```

#### ap_config.py — AP 热点 + HTTP 配网页

| 函数 | 作用 |
|------|------|
| `start_ap()` | 关 STA、开 AP 热点 `RELAY-SETUP-xxxx`，IP 设 192.168.4.1 |
| `run(cfg)` | 启动 HTTP 服务器（socket 手写，无 Flask），阻塞服务 |
| `_html_form(cfg)` | 生成配网 HTML 表单（WiFi + MQTT + Day7 Modbus 卡片） |
| `_parse_form(body)` | application/x-www-form-urlencoded 表单解析 |

**HTTP 服务器**：MicroPython 没有 Flask，用 `socket.socket()` 手写，监听 80 端口。GET 返回表单，POST 保存配置。

**Day7 新增卡片**：Modbus 采集配置 JSON 文本域，用户直接贴 JSON 配置。

#### 📌 Day7 踩坑：ESP32-C3 时钟系统（JetLinks 更新时间 1970 之谜）

**问题现象**：JetLinks 上所有属性的"更新时间"全是 `1970-01-01`，即使板子已经联网、MQTT 正常上报。

**根因一层层挖**（共 4 层坑，每修一层才暴露下一层）：

**坑 1：没 import `ntptime`**

Day5 固件 `main.py` 里根本没有 NTP 校时代码，`now_ms() = time.time() * 1000` 返回的是板子**开机秒数**（比如 120 秒 → JetLinks 收到 `1970-01-01 00:02:00`）。

修：WiFi 连上后调 `ntptime.settime()` 同步时间。

**坑 2：WiFi 已连时跳过了校时**

ESP32 STA 模式上电自动重连（记住了 WiFi 凭据），代码里：

```python
if _wlan.isconnected():
    return True   # ← 直接返回，跳过了 _ntp_sync()
```

修：已连也跑 `_ntp_sync()`。

**坑 3：`ntptime.settime()` 调了，但 `time.time()` 没变！（最坑）**

这是 **ESP32-C3 MicroPython 的一个特性**——板子上有两个"时钟"：

| 时钟 | 比喻 | 谁在管 |
|------|------|--------|
| `time.time()` | **秒表**（开机后从零数秒） | FreeRTOS tick counter |
| `machine.RTC().datetime()` | **电子表**（可以调日期） | RTC 硬件 |

`ntptime.settime()` 确实连了 NTP、确实更新了 RTC（电子表变成 2026-09-07），但 `time.time()` 继续从开机数——两个时钟互相不通信。

解决：**偏移量方案**，把"真实 epoch - 开机秒数"差记住，每次 `now_ms()` 就加：

```python
_NTP_OFFSET = 0          # NTP 同步后赋值

def _compute_epoch(dt):
    """从 RTC datetime 自己算 Unix epoch (MicroPython 没 calendar 模块)"""
    Y, M, D, H, Mi, S = dt[:6]
    total_days = (Y - 1970) * 365
    leaps = sum(1 for y in range(1970, Y)
                if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0)
    total_days += leaps
    days_in_month = [31,28,31,30,31,30,31,31,30,31,30,31]
    if (Y % 4 == 0 and Y % 100 != 0) or Y % 400 == 0:
        days_in_month[1] = 29
    total_days += sum(days_in_month[:M-1]) + (D-1)
    return total_days * 86400 + H*3600 + Mi*60 + S

def _ntp_sync():
    global _NTP_OFFSET
    ntptime.host = "ntp.aliyun.com"     # 国内比 pool.ntp.org 快
    ntptime.settime()
    rtc_dt = machine.RTC().datetime()    # 电子表 (已被 NTP 调准)
    real_epoch = _compute_epoch(rtc_dt)  # 从电子表算真实 epoch
    boot_counter = int(time.time())      # 秒表 (开机秒数)
    _NTP_OFFSET = real_epoch - boot_counter

def now_ms():
    return int((time.time() + _NTP_OFFSET) * 1000)
```

**坑 4：日历自己写 off-by-one，少了 365 天**

写 `_compute_epoch` 时犯了个低级数组分配错误：

```python
# ❌ 旧: Y-1-1970 个元素, Y=2026 时只有 55 个
DAYS_PER_YEAR = [365] * (Y - 1 - 1970)

# ✅ 新: 直接算, 不靠数组
total_days = (Y - 1970) * 365
```

差了 1 年（365 天 × 86400 秒），JetLinks 上显示 `2025-09-07`。

**坑 5：`mpremote cp` 报 Up to date 实际没覆盖**

`mpremote cp` 只比较文件 size，不比较内容。如果你在本地改了文件但 size 没变（或更小），它报 "Up to date" 直接跳过。修：先 `mpremote rm main.py` 再 `cp`。

```powershell
python -m mpremote connect COM5 rm main.py      # 先删板子上的
python -m mpremote connect COM5 cp main.py :/main.py   # 再强制上传
python -m mpremote connect COM5 reset           # 重启
```

### 时间戳验证速查

板子跑起来后串口应该能看到：

```
[main] WiFi already connected, IP: 192.168.30.145
[main] [TIME] real_epoch: 1788739596 boot: 842077xxx offset: 94666xxxx
[main] [TIME] now_ms() => 1788739596000  local(UTC): (2026, 9, 7, 8, 7, 16)
```

- `real_epoch` 应该在 1,788,7xx,xxx 量级（2026 年）
- `boot` 是开机秒数（~842,077,xxx，假 epoch）
- `now_ms()` 应该 ≈ `real_epoch * 1000`

如果 JetLinks 更新时间还是 1970：板子可能跑了旧 main.py → `rm + cp + reset` 强制覆盖。

#### modbus_gw.py — ⭐ Day7 新增，Modbus TCP 主站 + 时间片调度

这是 Day7 的核心，拆成三层：

**第一层：Modbus TCP 帧编解码**

```python
def _mbap(unit_id, pdu):
    """构造 Modbus TCP 帧 (MBAP头 + PDU)"""
    tid = _next_tid()                    # 事务ID，每次+1
    length = 1 + len(pdu)                # 长度 = 从站ID + PDU 长度
    mbap = struct.pack(">HHHB", tid, 0, length, unit_id)  # 大端打包
    return mbap + pdu, tid

def _parse_response(frame, expected_tid):
    """解析 Modbus TCP 响应帧"""
    tid, proto, length, unit_id = struct.unpack(">HHHB", frame[:7])  # 拆 MBAP 头
    # 校验 事务ID + 协议ID
    pdu = frame[7:7 + length]                                        # 拆 PDU
    ...

def _decode_registers(raw, count, dtype):
    """按 dtype 解码寄存器字节"""
    # uint16 / int16 / uint32 / int32 / float_be
    return struct.unpack(...)
```

Modbus TCP 帧结构：
```
MBAP 头 (7 字节)          PDU 载荷
┌─────────────────────┐ ┌──────────────────┐
│ 事务ID(2)│协议ID(2)  │ │功能码(1)+数据     │
│ 长度(2)  │从站ID(1) │ │                   │
└─────────────────────┘ └──────────────────┘
全部大端字节序 (">")
```

**第二层：Socket 连接管理（_SlaveConn）**

```python
class _SlaveConn:
    def __init__(self, host, port):
        self.sock = None          # socket 对象（None = 未连接）
        self.fail_count = 0       # 连续失败次数
        self.retry_after = 0      # 冷却截止时间（Unix ms）

    def _in_cooldown(self):
        return self.retry_after and time.ticks_ms() < self.retry_after

    def read_holding(self, unit_id, start_addr, count):
        if self._in_cooldown():   # ① 冷却中 → 直接跳过，零阻塞
            return None
        if self.sock is None:     # ② 先连一次
            if not self.connect():
                return None
        # ③ 发请求、等响应
        self.sock.sendall(frame)
        head = self._recv_exact(7)   # MBAP 头
        pdu = self._recv_exact(pdu_len)  # PDU
        ...
```

**冷却机制**：连续失败 3 次 → `retry_after = now + 30秒` → 30 秒内 `_in_cooldown()` 返回 True → 所有采集点直接返回 None，**不发起任何 socket 操作，主循环零阻塞**。

**第三层：时间片轮询调度（ModbusGateway）**

```python
class ModbusGateway:
    def poll_one(self):
        # ① 找最早到期的采集点
        now = time.ticks_ms()
        best = None
        for pt in self.points:
            if now >= pt["next_due"]:
                if best is None or pt["next_due"] < best["next_due"]:
                    best = pt

        if best is None:
            return   # 全部没到期，直接返回！

        # ② 只采这一个点
        regs = conn.read_holding(best["unit_id"], best["addr"], best["count"])
        val = _decode_registers(regs, best["count"], best["type"])
        if best.get("scale"):           # Day7: scale 缩放
            val = round(val * best["scale"], 2)
        self.values[best["key"]] = val

        # ③ 安排下次采集时间
        best["next_due"] = time.ticks_add(now, best["period"])
        #                 ↑ 注意: now + period，不是 next_due + period
        #                 锚定实际执行时刻，避免漂移累积
```

**为什么是 `now + period` 不是 `next_due + period`**：
- 如果用后者，每次实际采集晚的几十毫秒会累积，周期慢慢变长
- 用 `now + period` 把每次实际时刻当新基准，**漂移被重置**

**初始 next_due 偏移**：
```python
"next_due": time.ticks_add(time.ticks_ms(), 1000 + pi * 500)
# pi 是点在数组里的索引: 第1个+1000, 第2个+1500, 第3个+2000
# 启动瞬间天然错开，避免同时爆发
```

#### 📌 Day7 新增：JetLinks 下发属性 → 写 Modbus 从站寄存器

**为什么要加这个**：Day1-4 PC 模拟器时 JetLinks 下发温湿度能生效，是因为模拟器自己存 json 文件、自己改。ESP32 固件里温湿度是"读"Modbus 来的——ESP32 本身不"持有"温度值，之前 JetLinks 下发 `temperature: 26` 时 `apply_props` 里写着 `if not k.startswith("relay"): continue`，**所有非 relay key 直接跳过**。

**实现链路**：

```
JetLinks 编辑 temperature=26
    ↓ MQTT /properties/write: {"properties": {"temperature": 26}}
main.py on_msg → apply_props
    │ relay1~4 → relay_hw.set()         (GPIO)
    │ temperature → modbus_gw.write()    (Modbus 0x06) ← 新增!
    ↓
modbus_gw.py _write_info["temperature"]
    = {conn, unit_id=7, addr=0x0000, scale=0.1}
    reg_val = round(26.0 / 0.1) = 260   ← scale 反向换算
    ↓
Modbus TCP 功能码 0x06: 写 0x0000 = 260
    ↓
PC 模拟器 REGS[0] = 260 → 温度 = 26.0°C
    ↓
模拟器 drift() 在 260 附近继续小漂 (模拟真实设备)
ESP32 poll_one 下次读 → 25.8 → 26.1 → 26.3 → ...
```

**modbus_gw.py write 相关数据结构**：
```python
# 初始化时为每个带 key 的采集点建反向映射
self._write_info[pkey] = {
    "conn": conn,
    "unit_id": unit_id,
    "addr": addr,
    "scale": scale,
}

# JetLinks 下发 → 查表 → 写寄存器
def ModbusGateway.write(self, key, value):
    info = self._write_info[key]
    reg_val = int(round(value / info["scale"]))   # 反向: 用户值 → 寄存器值
    return info["conn"].write_holding(info["unit_id"], info["addr"], reg_val)
```

**main.py apply_props 扩展**：
```python
# Day7 之前: 只处理 relay 开头的 key
if not k.startswith("relay"): continue

# Day7 之后: 非 relay key 尝试写 Modbus
else:
    if modbus_gw.supports_write(k):
        if modbus_gw.write(k, float(v)):
            applied[k] = float(v)
```

**main.py invoke 功能调用也支持**（JetLinks"产品功能"面板）：
```python
# functionId = "set_temp", inputs = {"temperature": 26}
elif fid in ("set_temp", "set_temperature", "set_modbus"):
    value = params.get("temperature", params.get("温度", params.get("目标温度")))
    modbus_gw.write("temperature", float(value))

# functionId = "set_humidity" / "set_hum"
elif fid in ("set_humidity", "set_hum"):
    modbus_gw.write("humidity", float(value))
```

参数名兼容：支持 `temperature` / `温度` / `temp` / `目标温度` 四种写法，JetLinks 物模型里叫英文或中文都行。

#### main.py — 主循环整合

```python
# main.py 启动流程
def run_normal(cfg):
    # 1. 连 WiFi
    # 2. 连 MQTT (指数退避重连)
    # 3. 初始化 Modbus 网关 (Day7)
    gw = modbus_gw.init(cfg.get("modbus_slaves", []))
    # 4. 启动按键 Timer
    relay_hw.attach_buttons()
    # 5. 进入 mqtt_loop()

# main.py mqtt_loop() 简化版
def mqtt_loop():
    while True:
        relay_hw.check_keys()        # 扫描按键（Timer 已在后台跑，这里检查 config_request）
        if relay_hw.config_requested():
            break                    # 跳出 → 进 ap_config.run()

        _cli.check_msg()             # 非阻塞处理 MQTT 下行命令

        gw.poll_one()                # ⭐ Day7 时间片：只采 1 个 Modbus 点

        _maybe_ping()                # 每 25 秒发一次 MQTT ping

        _maybe_report()              # 属性变化检测 → 上报

# main.py 上报合并
def properties():
    props = dict(relay_hw.states())       # {'relay1':1, 'relay2':0}
    props.update(gw.collected())          # {'temperature':26.6}  ← Day7
    return props                           # {'relay1':1, 'temperature':26.6}
```

**断线重连（指数退避）**：
```python
backoff = 5
while True:
    try:
        wifi_connect()
        mqtt_connect()
        mqtt_loop()
    except Exception:
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)  # 5→10→20→40→60 封顶
```

#### config.py — 早期硬编码配置（已被 app_config 替代）

Day5 之前写死在代码里的配置，现在仅作参考。

#### main_modbus.py — 早期 Modbus 从站模式（测试用）

让 ESP32 自己当 Modbus TCP 从站，不用外部模拟器。功能简单，不支持配网。

#### main_mqtt.py — 早期 MQTT 直连模式（测试用）

Day5 之前的 MQTT 直连版本，硬编码配置。

#### serial_monitor.py — 串口监控辅助

旧版串口监控脚本，现在用 `start_serial.bat` 更方便。

---

## 八、Day6：双模式验证（MQTT 直连 vs Modbus+网关）

### 两种接入路线对比

| 对比项 | MQTT 直连 (Day5) | Modbus + 网关 (Day7) |
|--------|-----------------|---------------------|
| 网络结构 | ESP32 → JetLinks | ESP32 → Modbus 从站 + MQTT → JetLinks |
| 开发复杂度 | 较高（MQTT/TLS 协议在固件里） | 中等（固件简单，Modbus 协议简单） |
| 设备算力要求 | 较高（MQTT 栈 + TLS 加密） | 较低（仅 Modbus TCP） |
| 稳定性 | 受网络波动影响大 | 网关统一管理，更稳定 |
| 扩展性 | 每台设备独立上云 | 一网关可管理多台从站 |
| 适用场景 | 设备具备 WiFi/以太网 | 设备无联网能力，RS485 场景 |

### 路线验证

**MQTT 直连验证**（Day5 固件）：
1. 烧录 Day5 固件 → 配网 → MQTT 自动连 JetLinks
2. 平台下发 `set_relay` → 板子响应
3. 板子上报属性 → 平台显示

**Modbus+网关验证**（Day7 固件 + 外部模拟器）：
1. PC 启动 `modbus_slave_sim.py 5502 7`
2. ESP32 配网启用 Modbus，指向 PC IP:5502
3. 板子同时上报继电器状态 + Modbus 采集数据
4. MQTT 指令和 Modbus 采集不互相阻塞

---

## 九、Day7：Modbus 采集网关（核心功能详解）

![Day7 Modbus 网关运行](day7.jpg)

### 9.1 配置格式

配网页面 Modbus 卡片填 JSON：

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

### 9.2 字段速查

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

### 9.3 type 可选值

| type | 占寄存器数 | 范围 | 说明 |
|------|-----------|------|------|
| `uint16` | 1 | 0~65535 | 无符号整数 |
| `int16` | 1 | -32768~32767 | 有符号整数 |
| `uint32` | 2 | 0~4294967295 | 大整数 |
| `int32` | 2 | ±2^31 | 有符号大整数 |
| `float_be` | 2 | ±3.4×10³⁸ | IEEE 754 大端浮点 |

### 9.4 scale 缩放系数

传感器寄存器常以 ×10 存储（266 = 26.6°C）。配置 `"scale": 0.1` 后，固件上报 26.6。

JetLinks 物模型属性类型必须选 **double(双精度浮点)**，否则小数会被截断。

### 9.5 验收测试清单

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
| 9 | 冷却机制 | 关闭模拟器，日志出现"进入 3 秒冷却"且不再阻塞 |
| 10 | 配网改配置 | AP 模式改 Modbus JSON → 重启生效 |
| 11 | **JetLinks 下发温湿度** | 属性编辑面板改 temperature=26 → 模拟器日志出现 `写入寄存器 0x0000 : xxx → 260` → 板子日志出现 `write OK` → JetLinks 显示新值 |
| 12 | **产品功能调用** | 物模型加 `set_temp` / `set_humidity` 功能 → 功能调用面板输入值 → 同 #11 效果 |

### 9.6 JetLinks 产品功能配置（可选但推荐）

Day7 新增了 `set_temp` / `set_humidity` 功能调用支持，在 JetLinks 产品物模型里添加：

**功能 1：设置温度**
| 字段 | 值 |
|------|-----|
| 功能 ID | `set_temp` |
| 名称 | 设置温度 |
| 输入参数 | 名字 `temperature` 或 `温度`，类型 double |

**功能 2：设置湿度**
| 字段 | 值 |
|------|-----|
| 功能 ID | `set_humidity` |
| 名称 | 设置湿度 |
| 输入参数 | 名字 `humidity` 或 `湿度`，类型 double |

固件兼容 4 种参数名（`temperature` / `温度` / `temp` / `目标温度`），叫哪个都行。

### 9.7 模拟器稳定性改进

Day7 模拟器 `modbus_slave_sim.py` 两次迭代后变得稳定：

| 问题 | 修复 |
|------|------|
| **无 socket timeout** → 断线后线程泄漏 → 进程 OOM 崩溃 | `conn.settimeout(30)` + `socket.timeout` 捕获 → 30s 无报文自动清理 |
| **无服务异常恢复** → 任何 OS 异常直接死进程 | 外层 `while True + try/except OSError` → 3 秒后自动重启 |
| **冷却 30 秒太长** → 用户关开模拟器后等太久 | 从 15s → **3s**（足够模拟器重启，用户可接受） |

### 9.8 JetLinks 时间戳显示 8 小时差

JetLinks 显示时间比实际时间**少 8 小时**（比如板子 UTC epoch 正确，但 JetLinks 渲染成 UTC 时间而不是北京时间）——**这不是固件问题**。

根因：JetLinks 服务器/Docker 容器时区没设 `Asia/Shanghai`，它把 UTC epoch 直接按 UTC 格式渲染。

解决：
```yaml
# docker-compose.yml 加
environment:
  - TZ=Asia/Shanghai
# 或进容器手动
ln -sf /usr/share/zoneinfo/Asia/Shanghai /etc/localtime
```

固件上报的是 **正确 UTC Unix epoch 毫秒**（`1788739645000` = 2026-09-07 08:07:25 北京时间），符合 MQTT 协议规范——平台负责时区转换。

### 9.9 常见踩坑：关模拟器重开后 JetLinks 超时

完整的因果链：
```
你关模拟器窗口 → 进程消失
    ↓
板子 poll Modbus → ECONNREFUSED/RESET
    ↓
fail_count 累加: 1 → 2 → 3
    ↓
_on_fail() → retry_after = now + 3s → 进入冷却
    ↓
你重新开模拟器 → 5502 LISTENING ✅
    ↓
但板子还在冷却！poll_one 跳过所有点 → 不上报 → JetLinks 显示 --
    ↓
等 3 秒冷却到期后自动恢复
```

解决：
1. 冷却已从 15s → 3s，最多等 3 秒
2. 如果还嫌长，板子 reboot 也会清掉冷却状态

### 9.10 串口日志对照

| 日志行 | 含义 | 状态 |
|--------|------|------|
| `boot: ESP32 启动` | 硬件启动 | ✅ |
| `[main] 连接WiFi` | 配置有 WiFi | ✅ |
| `[main] WiFi OK, IP: xxx` | WiFi 连上 | ✅ |
| `[main] MQTT 已连接` | MQTT Broker 连上 | ✅ |
| `[main] Modbus 网关已启动, 采集点: 3` | Day7 网关初始化 | ✅ |
| `[modbus] temperature = 26.6` | **采集成功** | ✅ |
| `[modbus] 连接失败 ETIMEDOUT` | 从站不可达 | 检查防火墙/模拟器 |
| `[modbus] ... 进入 30 秒冷却` | 连续失败 3 次 | 等冷却自动重试 |

---

## 十、JetLinks MQTT 消息格式速查

### 10.1 上报（设备 → 平台）

```
Topic: /{productId}/{deviceId}/properties/report
示例:  /relay-cc/relaycc/properties/report
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

### 10.2 功能调用（平台 → 设备）

```
Topic: /relay-cc/relaycc/function/invoke
```

三种参数格式，代码全兼容：

**格式 A（JetLinks 自动生成）**：
```json
{"messageId":"t1","functionId":"set_relay","inputs":[{"name":"继电器编号","value":1},{"name":"状态","value":0}]}
```

**格式 B（MQTTX 手动推荐）**：
```json
{"messageId":"t1","functionId":"set_relay","inputs":{"relay":1,"state":0}}
```

**格式 C（中文参数名）**：
```json
{"messageId":"t1","functionId":"set_relay","inputs":{"继电器编号":1,"状态":0}}
```

### 10.3 功能回复（设备 → 平台）

```
Topic: /relay-cc/relaycc/function/invoke/reply
```

```json
{"messageId":"t1","success":"success"}
```

### 10.4 属性写入（平台 → 设备）

```
Topic: /relay-cc/relaycc/properties/write
```

```json
{"messageId":"t2","properties":{"relay1":0}}
```

### 10.5 属性读取（平台 → 设备）

```
Topic: /relay-cc/relaycc/properties/read
```

```json
{"messageId":"t3","properties":["relay1","relay2"]}
```

---

## 十一、常见问题排查

### 11.1 板子串口无输出

| 可能 | 解决 |
|------|------|
| mpremote 卡在 REPL 模式 | 按复位键重启 |
| 串口端口被占用 | 关掉其他串口监控程序 |
| 波特率不对 | 必须是 115200 |

### 11.2 WiFi 连不上

| 可能 | 解决 |
|------|------|
| 密码错 | 长按 SW1 重配网 |
| 信号弱 | 换近点或用手机热点 |
| 路由器限制 | 检查 MAC 地址过滤 |

### 11.3 MQTT 连接不上

| 可能 | 解决 |
|------|------|
| JetLinks 会话僵死 | 平台设备详情点"断开连接"→ 重启板子 |
| client_id 冲突 | 确保只有一个板子/模拟器用 relaycc |
| EMQX unretain 脏数据 | 代码已 publish("", retain=True) 清除 |

### 11.4 Modbus 采集失败

| 日志 | 原因 | 解决 |
|------|------|------|
| `ETIMEDOUT` | 从站不可达 | 防火墙放行 5502、模拟器是否启动 |
| `ECONNRESET` | 连接被从站拒绝 | 从站地址/端口是否正确 |
| 进入 30 秒冷却 | 连续失败 3 次 | 等冷却结束自动重试 |
| 数据值离谱 | 寄存器格式 | 检查 type 和 scale 配置 |

### 11.5 继电器控制无反应

| 可能 | 解决 |
|------|------|
| SW1 长按进配网失效 | 板子需在正常运行模式（不是 AP 模式） |
| MQTT 指令超时 | JetLinks 会话僵死 → 断开重连 |
| 继电器硬件电平 | 确认是高电平触发（实物已测） |
| 板子卡在 REPL | mpremote exec 后可能中断 main.py，重启板子 |

### 11.6 JetLinks 平台显示"有连接没数据"

| 可能 | 解决 |
|------|------|
| 属性 ID 拼写错误 | 物模型属性 ID 必须和固件上报 key 完全一致 |
| 数据类型不匹配 | relay1 是 int，temperature 带 scale 后是 double |
| 设备会话僵死 | 断开连接 → 重启板子 |
| 更新时间全是 **1970-01-01** | 板子没跑 NTP 校时 → 见 Day7 时钟系统那节 |

### 11.7 配网页面打不开 / 热点连不上

这是 Day8 踩得最多的坑，按现象对号入座：

#### 现象 A：长按后串口停在"SW1 长按5秒"，没有"热点已开放"，板子像死机

**根因**：旧固件在运行中检测到长按后，直接把 WiFi 从联网模式（STA）切成热点模式（AP）。但此时 MQTT、Modbus 的 socket 连接都还开着，切换网络模式会让板子挂死。模拟器连不上、网络状态异常时尤其容易触发。

**解决（已修复）**：改成**长按 → 写标记文件 `/force_ap` → `machine.reset()` 重启 → boot.py 在连 WiFi/MQTT 之前检测到标记 → 干净地进入配网**。和上电首次进配网走同一条路径，没有残留连接，不会挂死。

> 如果你板子上还是旧固件（长按后死机），重新刷一次最新固件即可。

#### 现象 B：串口显示"热点已开放"，但浏览器报 `ERR_ADDRESS_UNREACHABLE` / "无法访问此页面"

**根因**：你用**电脑**打开的 192.168.4.1，但电脑连的是办公 WiFi，**并没有连 ESP32 热点**。192.168.4.1 这个地址只有在"连上 RELAY-SETUP 热点的那个设备"上才能访问。

**解决**：
- 用**手机**连热点 `RELAY-SETUP-xxxx`，再用手机浏览器开 `http://192.168.4.1`
- 或用电脑连热点：电脑 WiFi 列表选 `RELAY-SETUP-xxxx` 连上后再开浏览器

#### 现象 C：手机连上热点了，但安卓弹"无法访问互联网"/网页转圈

**根因**：ESP32 热点本身不提供上网（它只是个配置页面），安卓检测到"这个 WiFi 上不了网"就想切回 4G。

**解决**：
- 弹出提示时点**"保持连接"/"仍要连接"**，别让它切走
- 关掉手机蜂窝数据/移动网络，强制只走 WiFi
- 浏览器地址必须是 **`http://192.168.4.1`**（不能是 https，也别让搜索引擎接管地址栏）

#### 现象 D：热点在 WiFi 列表里时有时无 / 搜不到

- ESP32 热点是 **2.4G**，确认手机/电脑支持并扫描 2.4G 网络
- 下拉刷新 WiFi 列表，或长按复位后重新长按 SW1
- 确认串口真的打印了"热点已开放"（没打印说明没进配网，回到现象 A）

| 速查 | 解决 |
|------|------|
| 手机用 4G 上网 | 关掉蜂窝数据，只走 WiFi |
| 用电脑开网页但电脑没连热点 | 改用手机，或让电脑连上热点 |
| 安卓弹"无法访问互联网" | 点"保持连接/仍要连接" |
| http:// 写成 https:// | 必须 http://192.168.4.1 |
| 长按后串口无"热点已开放" | 固件旧 → 刷最新固件（现象 A） |

### 11.8 MicroPython 兼容性坑

| 问题 | 解决 |
|------|------|
| `json.dumps(ensure_ascii=False)` 报错 | 去掉这个参数，MicroPython 默认不转义 |
| socket timeout 不能异步 | 时间片轮询 + 冷却机制 |
| 无完整标准库 | 手写 HTTP 服务器用 socket |
| 文件写入非原子 | 先写 .tmp 再 os.rename() |
| 不能真正多线程 | 单主循环 + 事件驱动 |

### 11.9 Day8 Bridge / 虚拟产品相关坑

| 现象 | 根因 | 解决 |
|------|------|------|
| Bridge 转发了，但 JetLinks 虚拟设备**收不到/不更新** | 虚拟产品 topic **缺前导 `/`** | 网关 topic 不带斜杠，**虚拟产品 topic 必须带 `/`**（`/lock-cc/lock001/properties/report`）。Bridge 已处理，别手动改 |
| 虚拟设备一直**离线**或属性不更新 | 设备 ID / 属性标识和路由表对不上 | 严格照 [13.2 路由表](#132-路由表最关键平台配置必须严格照这个)：lock001/light001/light002/ac001/sensorcc/human001/smoke001，属性 switch/temperature/humidity/detected/level |
| 物模型改了不生效 | 没点应用配置 | 产品物模型每次改完**必须点「应用配置」** |
| 温湿度/人体/烟雾是**固定值不变** | ① 飘动在 ESP32 端，旧固件没这逻辑；② Modbus 配置(寄存器地址/unit_id)和模拟器对不上读不到数据 | ① 刷最新固件；② 对照 [13.5](#135-modbus-配置可视化表单配网页) 检查 unit_id=7、温度 reg0、湿度 reg1、人体 reg4、烟雾 reg5 |
| 平台点门锁/灯，板子继电器**没反应** | Bridge 没在跑，或下行 topic 没订阅 | 确认 Bridge 窗口开着、打印了"订阅虚拟下行: xxx"；看 Bridge 有没有打印 `↓ ... → gateway {relayN: x}` |
| 人体/烟雾数据**一直不变** | 旧版模拟器没有人体/烟雾飘动 | 飘动已做到 ESP32 端，刷最新固件即可，不依赖模拟器版本 |

### 11.10 刷机 / 上传固件相关坑（Day8 实测）

| 现象 | 根因 | 解决 |
|------|------|------|
| `mpremote` 连不上板子、进不去 REPL | 板子正在跑 `main.py` 的 `while True` 主循环，占着 | 先 `esptool --port COM5 --chip esp32c3 erase-flash` 擦除，再刷固件、再 `mpremote cp` 传文件 |
| `mpremote cp` 报 `:/umqtt\simple.py` 这种路径错 | 目标路径用了反斜杠 `\`，被当成文件名 | 目标路径一律用**正斜杠** `:/umqtt/simple.py` |
| `mpremote cp` 提示 "Up to date" 但没更新 | 它只比文件大小不比内容，大小没变就跳过 | 先 `mpremote rm main.py` 删除板子上的，再 `cp` 上传 |
| 双击 `start_all.bat` 满屏乱码、命令被拆碎 | bat 是 UTF-8 编码，cmd 默认 GBK 解析，中文变乱码 | bat 用**纯英文 + GBK(ANSI) 编码**保存（本项目 start_all.bat 已改全英文） |
| COM 口找不到 / 突然消失 | USB 松动或被其他串口程序占用 | 重新插拔 USB；关掉其他串口监控窗口；`mpremote`/`esptool` 和串口监控不能同时开 |
| 模拟器跑本机还是实验室？ | — | 模拟器跑在哪台机器，板子配网里的 Modbus IP 就填那台机器的 IP（实验室填 192.168.20.59，本机填本机 IP） |

---

## 十二、快速启动命令速查

### 方式 1：双击启动脚本（推荐）

每个 dayx 文件夹里都有 start_*.bat 启动脚本，**在 Windows 上双击即可运行**。
所有脚本使用 ANSI 编码（Windows cmd 默认编码），中文不会乱码。

#### 脚本清单 + 冲突提示

| 脚本 | 功能 | 端口/COM | ⚠️ 启动前注意 |
|------|------|---------|--------------|
| `day1\start.bat` | Day1 温湿度模拟器 | TCP **5502** | **day7/start_modbus_sim.bat 和它互斥**（都占 5502）。脚本会检测，若已占用会弹窗问你是否继续 |
| `day2\start_relay.bat` | 继电器 JetLinks 模拟器 | — | 读 Day1 的 5502 端口，**建议 day1 先启动**再开这个。脚本会自动检测并提示 |
| `day2\start_sensor.bat` | 温湿度 JetLinks 模拟器 | — | 和 day2/start_relay.bat 不冲突，可同时运行 |
| `day2\start_ui.bat` | Web UI | TCP **8081** | **重复双击会占两个 8081**，脚本会检测提示 |
| `day5\flash_and_upload.bat` | 全流程烧录 | **COM口** | **关闭所有串口监控窗口**（start_serial.bat），否则 COM 口被占用导致烧录失败 |
| `day5\upload_only.bat` | 仅上传源码 | **COM口** | 同上：先关掉串口监控 |
| `day7\upload_modbus.bat` | Day7 增量上传 | **COM口** | 同上：先关掉串口监控 |
| `day7\start_modbus_sim.bat` | Modbus 从站 | TCP **5502** | 和 day1/start.bat 互斥（同端口）。脚本会检测并提示 |
| `esp32\start_serial.bat` 或 `day7\start_serial.bat` | 串口监控 | **COM口** | **mpremote / esptool 用之前必须关掉它**！COM 口同一时刻只能被一个程序打开 |

#### 最常用的启动组合

**场景 A：只测 Day1→Day2（PC 端完整链路）**
```
打开 3 个窗口:
  1. 双击 day1\start.bat           ← 先起温湿度 Modbus 从站
  2. 双击 day2\start_relay.bat     ← 再起继电器模拟器
  3. 双击 day2\start_ui.bat        ← 最后开 Web UI (浏览器自动打开)
```

**场景 B：测 Day5 固件烧录**
```
1. 先关闭所有串口监控窗口
2. 双击 day5\flash_and_upload.bat   ← 全流程一次搞定
3. 烧完后双击 esp32\start_serial.bat ← 看开机日志
```

**场景 C：测 Day7 Modbus 网关**
```
打开 3 个窗口:
  1. 双击 day7\start_modbus_sim.bat  ← PC 端 Modbus 从站（5502）
  2. 双击 day7\upload_modbus.bat     ← 板子上传 Day7 文件（关串口监控再做）
  3. 双击 esp32\start_serial.bat     ← 看板子日志确认 Modbus 数据
```

**场景 D：⭐ Day8 网关 + Bridge（一块板子变六个虚拟设备）**
```
前置: 板子已刷 Day8 固件并配好网(能连 MQTT + Modbus 模拟器)
  1. 双击 simulator\tools\start_all.bat
       → 自动弹两个窗口: ModbusSim(模拟器) + Bridge(协议转换)
  2. JetLinks 上确认 6 个虚拟产品(lock/light/ac/sensor/human/smoke)都建好
  3. 看 Bridge 窗口出现 ↑ 转发日志, 平台各设备属性开始更新
  4. 平台点门锁/灯开关 → 板子继电器咔哒(下行回流)

改传感器基准值(在能连模拟器的电脑上):
  python simulator\tools\set_modbus.py 25 60 1 50
```

#### 端口/COM 冲突速查表

| 资源 | 占用者 | 冲突方 | 现象 |
|------|--------|--------|------|
| TCP 5502 | `day1/start.bat` 或 `day7/start_modbus_sim.bat` | 另一个 | 第二个启动的会报占用警告；脚本会显示占用进程名+PID |
| TCP 8081 | `day2/start_ui.bat` | 重复启动 | OSError: WinError 10048 通常每个套接字只允许使用一次 |
| COM口 | `start_serial.bat` | `flash_and_upload.bat` / `upload_only.bat` / `upload_modbus.bat` | 烧录/上传脚本报 Permission denied 或 could not open port |

#### FAQ：没开过 day1 模拟器，为什么报 5502 被占用？

- **不是 ESP32 实物占用**。板子是 Modbus TCP 客户端，只会主动"连出"到 PC 的 5502，自己从不监听该端口，硬件不可能占用。
- 真正原因：**上次测试的模拟器进程还在后台跑**（cmd 窗口没关，或 python.exe 残留）。
- 现在的启动脚本会自动查出占用者的**进程名和 PID** 并显示，例如：
  `[警告] 端口 5502 已被占用: python.exe  PID=12832`
- 处理：确认旧窗口不要了 → `taskkill /F /PID <显示的PID>` → 重新启动脚本。
- 注意：模拟器绑端口时用了 `allow_reuse_address`，被占用时选"仍然启动"能成功绑上，但**两个进程会同时抢同一端口**（连接随机分配），测试结果会错乱——报占用时优先选 N 并先杀旧进程。

### bat 脚本报错排查

如果你双击 bat 后看到一堆 `不是内部或外部命令` 的乱码报错，**99% 是 bat 文件换行符或编码问题**。本项目已修复，了解原因避免自己改坏：

#### Windows bat 的两个硬性要求（其他平台无所谓）

| 要求 | 正确 | 错误 | 现象 |
|------|------|------|------|
| **换行符必须 CRLF** | `\r\n` (0D 0A) | `\n` (0A) 只有 LF | cmd 把多行合并成一行，`set /p PORT=请输入...` 整个被当命令执行 → `'请输入' 不是内部或外部命令` |
| **编码必须 ANSI (GBK)** | 用系统默认代码页 936，**不要写 chcp** | UTF-8 无 BOM，或 GBK 文件里加 `chcp 65001` | GBK 中文被按 UTF-8 解释 → 全屏 `????` 乱码 |

#### 验证脚本换行符

```powershell
# 用 Python 检查 bat 是否有 LF 换行（不应该有）
python -c "import glob; [print(('CRLF OK' if b'\r\n' in open(f,'rb').read() else '!!! LF 坏了 !!!')+' '+f) for f in glob.glob('simulator/**/*.bat', recursive=True)]"
```

输出应为全部 `CRLF OK`。如果有 `!! LF 坏了 !!`：

```powershell
# 修复：强制转 CRLF
$content = [System.IO.File]::ReadAllText("脚本路径.bat", [System.Text.Encoding]::Default)
$content = $content -replace "`r?`n", "`r`n"
[System.IO.File]::WriteAllText("脚本路径.bat", $content, [System.Text.Encoding]::Default)
```

#### 其他启动报错速查

| 报错现象 | 原因 | 解决 |
|---------|------|------|
| 双击后 cmd 一闪而过 | 脚本崩溃了 | 不要双击，先打开 cmd 再拖入 bat 执行，能看到完整错误 |
| `'python' 不是内部或外部命令` | Python 未加 PATH | `where python` 查有没有，没有就重装勾上 Add to PATH |
| `'mpremote'` / `'esptool'` 找不到 | 没装 | `pip install mpremote esptool pyserial` |
| 双击没反应（窗口不弹） | 文件关联坏了或编码完全错乱 | 右键→打开方式→cmd.exe，或用 PowerShell `& "path\script.bat"` |
| `set /p` 提示文字乱码 | 编码不是 ANSI | 转回 ANSI 或去掉中文提示 |

### 方式 2：手动命令

```powershell
# === PC 端 ===
# Modbus 从站模拟器
cd simulator\tools
python modbus_slave_sim.py 5502 7

# 继电器模拟器 (Day2)
cd simulator\day2
python relay_simulator_jl.py

# 继电器 Web UI
python relay_ui.py

# === ESP32 固件 ===
# 擦除旧固件
python -m esptool --port COM5 erase_flash

# 烧录 MicroPython
python -m esptool --port COM5 --chip esp32c3 flash_mode dio --flash_freq 40m flash_id simulator/esp32/_firmware/ESP32_GENERIC_C3-v1.29.0.bin

# 上传源码 (从 simulator/esp32 目录)
cd simulator\esp32
python -m mpremote connect COM5 cp boot.py :/boot.py
python -m mpremote connect COM5 cp app_config.py :/app_config.py
python -m mpremote connect COM5 cp relay_hw.py :/relay_hw.py
python -m mpremote connect COM5 cp ap_config.py :/ap_config.py
python -m mpremote connect COM5 cp modbus_gw.py :/modbus_gw.py
python -m mpremote connect COM5 cp main.py :/main.py

# 板子重启
python -m mpremote connect COM5 reset

# 查看配置
python -m mpremote connect COM5 exec "import app_config; print(app_config.load())"
```

---

## 十三、Day8：网关 + Bridge（一台板子变六个设备）

![Day8 网关+Bridge 架构]

前面 Day1~7，一块 ESP32 板子在 JetLinks 上就是**一个设备**（产品 `relay-cc` / 设备 `relaycc`），所有继电器和传感器数据都堆在这一个设备里。

但真实场景里，4 路继电器其实是 4 个不同的东西（门锁、灯、灯、空调），温湿度/人体/烟雾又是 3 类传感器。Day8 用一个 **Python Bridge（协议转换桥）** 让一块板子在平台上"分身"成 **6 个虚拟产品、7 个虚拟设备**。

### 13.1 整体架构

```
ESP32 板子 (产品 relay-cc / 设备 relaycc)
  │  一条 MQTT 消息里塞了所有数据:
  │  {relay1:1, relay2:0, relay3:1, relay4:0,
  │   temperature:26.5, humidity:60, human:1, smoke:2}
  ▼
Python Bridge (gateway_bridge.py, 电脑上一直跑)
  │  ① 上行: 订阅 relay-cc/relaycc/#, 按路由表拆成 7 份分别转发
  │  ② 下行: 订阅 6 个虚拟产品的控制 topic, 路由回板子
  ▼
JetLinks 上 6 个虚拟产品 / 7 个设备 (各自独立的页面、物模型)
```

### 13.2 路由表（最关键，平台配置必须严格照这个）

Bridge 里硬编码了一张路由表 `UP_ROUTING`（`simulator/tools/gateway_bridge.py`）：

| 网关上报的 key | → 虚拟产品 | → 设备 ID | → 属性标识 | 代表什么 |
|----------------|-----------|-----------|-----------|---------|
| `relay1` | lock-cc | **lock001** | `switch` | 门锁 |
| `relay2` | light-cc | **light001** | `switch` | 灯 1 |
| `relay3` | light-cc | **light002** | `switch` | 灯 2 |
| `relay4` | ac-cc | **ac001** | `switch` | 空调 |
| `temperature` | sensor-cc | **sensorcc** | `temperature` | 温度 |
| `humidity` | sensor-cc | **sensorcc** | `humidity` | 湿度 |
| `human` | human-cc | **human001** | `detected` | 人体感应(0/1) |
| `smoke` | smoke-cc | **smoke001** | `level` | 烟雾等级(0~100) |

> ⚠️ **平台上的"设备 ID"和"属性标识"必须和这张表一个字母都不差**，否则 Bridge 转发了，平台也会因为对不上而静默丢弃。这是新手最容易踩的坑。

### 13.3 JetLinks 平台配置（6 个虚拟产品）

对每一个虚拟产品，重复下面的步骤（以门锁 lock-cc 为例）：

1. **产品管理 → 新建产品**
   - 产品 ID：`lock-cc`（必须和路由表一致）
   - 设备类型：**直连设备**
   - 认证方式：**不认证**
2. **进产品 → 物模型 → 加属性**
   - 门锁/灯/空调：加一个属性，标识 `switch`，类型 int，读写
   - 温湿度 sensor-cc：加两个属性 `temperature`、`humidity`，类型 **double**，只读
   - 人体 human-cc：属性标识 `detected`，类型 int，只读
   - 烟雾 smoke-cc：属性标识 `level`，类型 int，只读
3. **⚠️ 点「应用配置」**（物模型改完一定要点，否则不生效！）
4. **产品 → 设备 → 新增设备**，设备 ID 严格按路由表（如 `lock001`）

> 📌 **虚拟产品的 topic 必须带前导 `/`**。网关 topic 是 `relay-cc/relaycc/...`（不带斜杠），但虚拟产品 Bridge 转发时用的是 `/lock-cc/lock001/properties/report`（**带前导斜杠**）。这是 JetLinks 对"第三方/虚拟设备"的要求，Bridge 代码里已经处理好了，你只要知道别手动去改就行。

### 13.4 一键启动（电脑端）

```powershell
cd simulator\tools
# 双击 start_all.bat, 或手动:
start_all.bat
```

会弹出两个 cmd 窗口：

| 窗口 | 跑什么 | 作用 |
|------|--------|------|
| **ModbusSim** | `python -u modbus_slave_sim.py 5502 7` | Modbus 从站模拟器（温湿度/人体/烟雾寄存器） |
| **Bridge** | `python -u gateway_bridge.py` | 订阅网关 + 6 个虚拟产品，做拆分/回流 |

Bridge 窗口正常的话会打印：
```
[Bridge] 已连接 172.16.4.211:9783
  订阅网关: relay-cc/relaycc/#
  订阅虚拟下行: lock-cc (1 设备)
  订阅虚拟下行: light-cc (2 设备)
  订阅虚拟下行: ac-cc (1 设备)
  订阅虚拟下行: sensor-cc (1 设备)
  订阅虚拟下行: human-cc (1 设备)
  订阅虚拟下行: smoke-cc (1 设备)
```

> 💡 日志里 `light-cc (2 设备)` 的数字是**该产品下的设备数量**（light 产品下有 light001、light002 两个灯）。

有数据时会看到转发日志：
```
  ↑ sensor-cc/sensorcc report: {'temperature': 26.5, 'humidity': 60.2}
  ↑ human-cc/human001 report: {'detected': 1}
  ↓ lock-cc/lock001 write {'switch': 0} → gateway {'relay1': 0}   ← 平台点门锁, 回流控制继电器1
```

### 13.5 Modbus 配置可视化表单（配网页）

Day8 把配网页面的 Modbus 配置从"贴一大段 JSON"改成了**可视化表单**（`ap_config.py`）：

- 每个**从站**一张卡片：填服务器 IP、端口、单元 ID，可勾选"启用"、可"删除从站"、可"+ 添加从站"
- 每个从站下可加多个**寄存器采集点**：寄存器地址、采集周期(ms)、上报 key、上报产品、是否可写，可单独删除
- 深色主题，手机上也能看清
- 点"保存并应用"立即写入板子 NVS 并重启，断电不丢

本项目实际的 Modbus 配置（板子 `config.json`）：

| 从站 | 值 |
|------|-----|
| 服务器 IP | `192.168.20.59`（实验室跑模拟器的机器） |
| 端口 | `5502` |
| 单元 ID (unit_id) | **7** |

| 采集点 | 寄存器地址 | key | 周期 | scale |
|--------|-----------|-----|------|-------|
| 温度 | 0x0000 (reg0) | temperature | 3000ms | 0.1 |
| 湿度 | 0x0001 (reg1) | humidity | 5000ms | 0.1 |
| 人体 | 0x0004 (reg4) | human | 3000ms | 1 |
| 烟雾 | 0x0005 (reg5) | smoke | 3000ms | 1 |

> ⚠️ **寄存器地址和 unit_id 必须和模拟器对得上**。模拟器是 unit_id=7、温度在 reg0、湿度在 reg1、人体在 reg4、烟雾在 reg5。配错了（比如 unit_id 写成 4、温度配成 reg3）板子读不到数据，平台上就是固定值/不更新。

### 13.6 ESP32 端数据飘动（为什么数据不是固定值）

真实传感器的值会一直轻微变化。为了演示效果，飘动逻辑做在了 **ESP32 固件里**（`modbus_gw.py` 的 `_apply_drift()`），板子每次读到寄存器值后叠加一层小扰动：

| 传感器 | 飘动策略 |
|--------|---------|
| temperature / humidity | ±2% 随机乘法扰动（基准值不变，围绕真实值小幅波动） |
| human（人体） | 每次 5% 概率翻转 0/1（模拟有人走动） |
| smoke（烟雾） | ±3 波动，限制在 0~100 |

**为什么做在板子端而不是模拟器端？** 这样不管实验室那台模拟器是什么版本、有没有更新，只要板子在跑，平台上的数据就会飘动，不依赖外部电脑。模拟器端也有一层飘动（见 [第三章寄存器布局](#寄存器布局)），两层叠加效果更自然。

> 注意：飘动是**围绕基准值的小波动，不会改变基准**。想改基准温度（比如从 30°C 拉回 25°C），要用 `set_modbus.py` 写模拟器寄存器。

### 13.7 手动改传感器值（set_modbus.py）

在**能连到模拟器所在机器（192.168.20.59）**的电脑上运行：

```powershell
cd simulator\tools

# 位置参数: 温度 湿度 人体 烟雾
python set_modbus.py 25 60 1 50

# 也可以单独设置某一个
python set_modbus.py --temp 30       # 只改温度 30.0°C
python set_modbus.py --humidity 80   # 只改湿度 80%RH
python set_modbus.py --human 0       # 人体: 0=无人, 1=有人
python set_modbus.py --smoke 30      # 烟雾等级 0~100
```

写入后模拟器的值被更新，板子下次采集就会读到新基准，然后围绕它继续飘动。

### 13.8 Day8 文件清单

| 文件 | 作用 |
|------|------|
| `simulator/tools/gateway_bridge.py` | **Bridge 协议转换**：上行拆分到 6 虚拟产品，下行回流到网关 |
| `simulator/tools/modbus_slave_sim.py` | Modbus 从站模拟器（温湿度/人体/烟雾/继电器/电流电压，带飘动） |
| `simulator/tools/set_modbus.py` | 手动写模拟器寄存器（温湿度/人体/烟雾） |
| `simulator/tools/start_all.bat` | 一键启动模拟器 + Bridge（双击即可） |
| `simulator/esp32/*.py` | ESP32 网关固件（boot/main/ap_config/modbus_gw/relay_hw/app_config） |
| `simulator/day8/` | Day8 归档副本（esp32_firmware + tools），与主目录同步 |

### 13.9 Day8 验收清单

| # | 测试项 | 通过标志 |
|---|--------|---------|
| 1 | 模拟器启动 | ModbusSim 窗口显示 `0.0.0.0:5502 (unit_id=7)` |
| 2 | Bridge 启动 | 打印"已连接"+ 订阅网关 + 订阅 6 个虚拟产品 |
| 3 | 板子联网上报 | 串口 `[modbus] temperature/humidity/human/smoke = ...` |
| 4 | 上行拆分 | Bridge 打印 `↑ sensor-cc/sensorcc report: {...}` |
| 5 | 平台多设备 | JetLinks 上 lock/light/ac/sensor/human/smoke 6 个产品的属性都在更新 |
| 6 | 数据飘动 | 温湿度/人体/烟雾数值持续变化，不是固定值 |
| 7 | 下行控制 | 平台点门锁/灯的开关 → 板子继电器咔哒 + Bridge 打印 `↓ ... → gateway {relayN: x}` |
| 8 | 配网表单 | 长按 SW1 进配网，可视化表单能增删从站/采集点 |

---

## 十四、Day9：SQLite 动态路由 + Web 管理后台 + 权限系统 + 实物控制台

> **完整详细版见 [simulator/day9/README.md](simulator/day9/README.md)**（面向新手零基础的完整运行指南、代码文件说明、踩坑记录）

### 14.1 Day9 解决什么问题

Day8 时 Bridge 路由表硬编码在 `gateway_bridge.py` 里——每新增一个虚拟设备都要改代码 + 重启。Day9 用 SQLite 做动态路由 + Flask Web 管理后台 + 完整权限系统，让**一块物理网关的 7 个虚拟设备映射关系可以通过浏览器零代码管理**。

| 对比项 | Day8 | Day9 |
|--------|------|------|
| 路由表存储 | Python 源码硬编码 | SQLite `db/iot_platform.db` |
| 新增映射 | 改代码 + 重启 | Web 页面点新增 + Bridge 热刷新（5 秒） |
| 用户系统 | 无 | admin / user 两角色 + db 层源头校验 |
| 管理界面 | 无 | Flask 深色主题 Web（8 个页面） |
| 实物控制台 | 无 | **MQTT 直连下发继电器命令** + 传感器状态缓存 |
| 在线追踪 | 无 | 登录会话表 + 5 分钟超时 + 新登录踢旧 session |
| 采集点配置 | 无 | Web 编辑 `config.json` 可视化表单 |
| 敏感信息 | 无保护 | 普通用户看原始 JSON 时密码脱敏 `******` |
| MQTT 凭据 | 3 处硬编码 | 统一从 `config.json` 读取（db.py `load_gateway_config()`） |

### 14.2 运行

```powershell
# 方式 1：一键启动（推荐）
cd simulator\day9
start_all.bat   # 自动起 3 个窗口：ModbusSim + Bridge + Web

# 方式 2：手动
cd simulator\day9
python db.py                          # 首次建库
python modbus_slave_sim.py 5502 7     # 模拟器
python gateway_bridge.py --hot-reload # Bridge + 热刷新
python web\app.py                     # Web 管理后台
```

浏览器打开 **http://127.0.0.1:8081**

默认账号：
- **admin / admin123** — 全部权限
- **user / user123** — 只读

### 14.3 8 个 Web 页面

| 页面 | URL | admin | user |
|------|-----|-------|------|
| 看板 | /dashboard | ✓ 可点击 stat-card 跳转 | ✓ |
| 实物控制台 | /devices | ✓ 继电器开/关/全关 + 传感器状态 | 只读（看状态，不能点继电器） |
| 映射管理 | /mappings | ✓ 增/改/删/启用禁用 | 只读（按钮隐藏） |
| 采集点配置 | /config-points | ✓ 编辑 WiFi/MQTT/Modbus 采集点 | 只读（原始 JSON 密码脱敏） |
| 在线用户 | /sessions | ✓ 在线列表 + 历史 | ✓ |
| 用户管理 | /users | ✓ 增/改角色/重置密码/删 | **侧边栏完全隐藏** |
| 登录 | /login | ✓ | ✓ |
| 退出 | /logout | ✓ | ✓ |

### 14.4 核心技术点

- **SQLite 动态路由**：`device_mappings` 表存 8 条映射，Bridge 启动加载 + `--hot-reload` 每 5 秒自动刷新
- **四层 db.py**：`device_mappings` / `users` / `login_sessions` / `device_status`，Bridge 和 Web 共用
- **三层权限防御**：`@admin_required` 路由装饰器 → 前端 `{% if admin %}` 隐藏按钮 → **db.py 源头正则校验**（任何调用方式都拦）
- **登录会话管理**：`kick_user_sessions()` 新登录踢旧的 + `list_online_users()` 5 分钟超时过滤
- **MQTT 凭据统一**：`load_gateway_config()` 函数只从 `config.json` 读，Bridge + Web 都用它
- **表单正则解析**：多下划线字段（`slave_0_period_ms_0`）用 `re.match(r'^slave_(\d+)_(addr|key|period_ms|type|scale|count|write)_(\d+)$')` 而不是 `split('_')`

### 14.5 踩坑速查

Day9 实测修了 9 个 bug，**完整踩坑记录 + 根因分析 + 修复代码见 [day9/README.md 踩坑章节](simulator/day9/README.md#踩坑记录day9-实测--修复)**：

| 坑 | 严重度 | 一句话 |
|----|--------|--------|
| 采集点保存丢 period_ms | 🔴 | `split('_')` 把 `period_ms` 拆成 `['period','ms']` → `int('ms')` 报错跳过整条记录 |
| 普通用户看密码明文 | 🔴 | 原始 JSON 直接渲染 `config \| tojson` → user 也能看到 `123456` / `yh82922868` |
| db 层无校验被绕过 | 🔴 | 只在 Flask route 加校验 → 直接 `from db import add_user` 能写脏数据 |
| 关浏览器后永远在线 | 🟡 | 只认 `status='online'`，没考虑超时 |
| 同一用户堆 N 条 session | 🟡 | `start_session()` 无条件新建，没踢旧的 |
| MQTT 3 处硬编码不同步 | 🟡 | 改一处忘改另外两处 |
| config.json.bak 被 git 追踪 | 🟢 | `.gitignore` 对已追踪文件无效 → `git rm --cached` |
| 弹窗 DOM 泄露给 user | 🟢 | 按钮隐藏但 HTML 还在 |
| display_name 可选项被必填校验拦 | 🟢 | `_validate` 的空字符串检查误伤可选字段 |

---

## 十五、Day10：场景联动 + 告警机制

> **完整详细版见 [simulator/day10/README.md](simulator/day10/README.md)**（面向新手的运行指南、数据库设计、规则执行流程、验收清单）

### 15.1 Day10 解决什么问题

Day9 平台是「被动展示」——数据进来只是展示，设备出问题不会自动处理。Day10 新增**场景规则引擎**和**告警三态流转**，让平台具备「主动联动 + 主动告警」能力：温度过高自动断电、有人自动开灯、烟雾超标紧急告警。

| 对比项 | Day9 | Day10 |
|--------|------|-------|
| 数据上报 | 展示 | 展示 + 触发规则评估 |
| 设备控制 | 手动点击 | 手动 + 自动联动 |
| 异常处理 | 无 | 规则触发告警 + 自动动作 |
| 告警管理 | 无 | 三态流转（未确认→已确认→已清除） |
| SQLite 表 | 4 张 | 6 张（新增 scene_rules + alarm_records） |
| Web 路由 | 8 个 | 19 个（新增 /scenes /alarms 系列） |

### 15.2 一键运行

```bat
cd simulator\day10
start_all.bat
```

打开 http://127.0.0.1:8081 → 登录 admin/admin123 → 访问 /scenes 和 /alarms。

### 15.3 核心机制

**场景规则结构**：`IF [采集点] [运算符] [阈值] THEN [动作] + 产生 [级别] 告警`

**预填充 4 条示例规则**：

| 规则 | 条件 | 动作 | 级别 |
|------|------|------|------|
| 高温自动断电 | temperature > 35 | all_relay_off | critical |
| 烟雾告警联动 | smoke > 50 | all_relay_off | critical |
| 有人自动开灯 | human == 1 | set_relay(relay2, 1) | info |
| 无人自动关灯 | human == 0 | set_relay(relay2, 0) | info |

**告警三态流转**：active（未确认）→ acknowledged（已确认）→ cleared（已清除）

**冷却机制**：规则触发后进入 cooldown_sec 秒冷却期，避免传感器抖动导致频繁触发。

### 15.4 关键技术点

- **规则评估在 Bridge 端**：`evaluate_scene_rules()` 在 `handle_gateway_properties_report()` 中对每个上报的 key 调用，命中后由 `execute_scene_actions()` 执行动作 + 产生告警
- **动作类型**：set_relay（单路控制）、all_relay_off（全关）、all_relay_on（全开）、send_alarm（仅告警不控制设备）
- **告警通知双通道**：SQLite 记录（持久化）+ MQTT `/system/alarm/notify` topic（实时通知）
- **看板角标轮询**：前端每 30 秒调 `/api/alarm-stats`，未确认告警 > 0 时导航栏告警图标显示红色脉冲点
- **输入校验在 db.py 源头**：规则名称、采集点 key、运算符、告警级别、动作类型全部正则校验，防止绕过 Flask route 直接调用

### 15.5 验证场景联动

```bat
:: 终端1: 设置温度=36°C (写360, 因为scale=0.1)
python set_modbus.py 360 600 1 50

:: 终端2: 查看告警
:: 浏览器打开 http://127.0.0.1:8081/alarms
:: 看到 critical 告警「高温自动断电」→ 点击确认 → 点击清除
```

---

## 附录：ESP32 固件数据流全景

```
┌─────────────────┐     Modbus TCP 0x03      ┌─────────────────┐
│ Modbus TCP 从站  │ ←────────────────────── │ ESP32 主站       │
│ (传感器/模拟器)   │  poll_one() 读寄存器     │  modbus_gw.py    │
│  reg0=266 (26.6°C)│ ──────────────────→    │  解码+scale=0.1  │
└─────────────────┘                          │  → 26.6         │
                                             └────────┬────────┘
                                                      │
                                             properties() 合并
                                                      │
                                             ┌────────▼────────┐
                                             │ MQTT 上报 payload │
                                             │ {                │
                                             │   relay1: 1,    │
                                             │   relay2: 0,    │
                                             │   temperature: 26.6,  ← Modbus
                                             │   humidity: 75.1     ← 和继电器
                                             │ }                     一条消息
                                             └────────┬────────┘
                                                      │ MQTT
                                             ┌────────▼────────┐
                                             │ JetLinks 平台    │
                                             │ 物模型属性显示    │
                                             └─────────────────┘
```

**同时**，MQTT 下行命令（set_relay/all_on 等）和按键扫描在 poll_one() 的前后执行，全程不阻塞。
