# Day8 · 网关 + Bridge（一块板子变六个设备）

## 当天目标

Day7 时，一块 ESP32 板子在 JetLinks 平台上只是**一个设备**（产品 `relay-cc` / 设备 `relaycc`），4 路继电器和温湿度全堆在这一个设备里。

但真实智能家居里，4 路继电器其实是 4 个不同的电器（门锁、灯、灯、空调），温湿度/人体/烟雾又是 3 类传感器——它们本该是平台上**各自独立的设备**，有各自的页面、图标、物模型。

Day8 的目标：用一个 **Python Bridge（协议转换桥）程序**，让**一块物理 ESP32 板子，在 JetLinks 上"分身"成 6 个不同类型的虚拟产品、7 个虚拟设备**。

- 板子只负责"采数据 + 控继电器"，把所有数据打成**一条** MQTT 消息上报
- Bridge 程序订阅这条消息，按一张**路由表**拆成 7 份，分别上报给 7 个虚拟设备
- 平台上对虚拟设备的控制（比如点"开门锁"），Bridge 再路由回板子对应的继电器

## 最终架构

```
┌──────────────┐  Modbus TCP   ┌──────────────────────┐
│ Modbus 模拟器 │ ←读 reg0/1/4/5→│   ESP32-C3 网关       │
│ (温湿度/人体/ │              │   (产品 relay-cc      │
│  烟雾)        │              │    设备 relaycc)      │
│ 192.168.20.59 │              │                      │
│   :5502       │              │  4路GPIO继电器        │
└──────────────┘              │  + Modbus采集         │
                              └──────────┬───────────┘
                                         │ 一条 MQTT 消息(所有数据混在一起)
                                         │ relay-cc/relaycc/properties/report
                                         ▼
                              ┌──────────────────────┐
                              │  Python Bridge        │  ← 在电脑上一直跑
                              │  gateway_bridge.py    │
                              │  ① 上行: 按路由表拆分  │
                              │  ② 下行: 控制回流      │
                              └──────────┬───────────┘
                                         │ 每个虚拟设备一条 topic(带前导 /)
           ┌──────────┬──────────┬───────┴────────┬──────────┬──────────┐
           ▼          ▼          ▼                ▼          ▼          ▼
       门锁 lock-cc 灯 light-cc 空调 ac-cc     温湿度      人体 human  烟雾 smoke
       lock001      light001    ac001        sensor-cc    human001    smoke001
                    light002                   sensorcc
           └──────────────────────────────────────────────────────────┘
                                          ▼
                              JetLinks 平台 (172.16.4.211)
                                          ▼
                                  浏览器看数据 / 点按钮
```

## 路由表（最最关键，平台配置必须一字不差）

Bridge 里硬编码了这张表（`tools/gateway_bridge.py` 的 `UP_ROUTING`）。**JetLinks 上建产品/设备/属性时，ID 必须和这张表完全一致**，否则数据对不上会被平台静默丢弃。

| 板子上报的 key | → 虚拟产品 ID | → 设备 ID | → 属性标识 | 数据类型 | 代表 |
|----------------|--------------|-----------|-----------|---------|------|
| `relay1` | `lock-cc` | `lock001` | `switch` | int 读写 | 门锁 |
| `relay2` | `light-cc` | `light001` | `switch` | int 读写 | 灯 1 |
| `relay3` | `light-cc` | `light002` | `switch` | int 读写 | 灯 2 |
| `relay4` | `ac-cc` | `ac001` | `switch` | int 读写 | 空调 |
| `temperature` | `sensor-cc` | `sensorcc` | `temperature` | double 只读 | 温度 |
| `humidity` | `sensor-cc` | `sensorcc` | `humidity` | double 只读 | 湿度 |
| `human` | `human-cc` | `human001` | `detected` | int 只读 | 人体(0无人/1有人) |
| `smoke` | `smoke-cc` | `smoke001` | `level` | int 只读 | 烟雾等级(0~100) |

> 一共 **6 个产品、7 个设备**（light-cc 产品下有 2 个灯设备）。

## 代码结构（day8 文件夹里有什么）

```
day8/
├── esp32_firmware/                  ← 刷进 ESP32 板子的固件（板子端）
│   ├── _firmware/
│   │   └── ESP32_GENERIC_C3-v1.29.0.bin   ← MicroPython 解释器(整块刷)
│   ├── umqtt/
│   │   ├── __init__.py
│   │   └── simple.py                      ← MQTT 客户端库(第三方)
│   ├── boot.py                            ← 启动入口:连WiFi/MQTT,判断进配网
│   ├── main.py                            ← 主程序:继电器+Modbus采集+上报循环
│   ├── ap_config.py                       ← 配网热点+网页(可视化Modbus表单)
│   ├── app_config.py                      ← 配置读写(config.json持久化)
│   ├── modbus_gw.py                       ← Modbus主站:读寄存器+数据飘动
│   ├── relay_hw.py                        ← 4路继电器GPIO+按键扫描
│   └── config.json                        ← 当前配置(WiFi/MQTT/Modbus)
│
└── tools/                           ← 在电脑上运行的程序（电脑端）
    ├── gateway_bridge.py                  ← ⭐ Bridge:拆分上行+回流下行
    ├── modbus_slave_sim.py                ← Modbus从站模拟器(温湿度/人体/烟雾)
    ├── set_modbus.py                      ← 手动改模拟器里的传感器值
    ├── detect_com.py                      ← 自动探测 ESP32 的 COM 口号
    ├── start_all.bat                      ← ⭐ 一键启动:模拟器+Bridge
    └── start_serial.bat                   ← 串口日志监控(看板子打印)
```

## 每个代码文件是干什么的（新手逐个看）

### 板子端（esp32_firmware/，刷进 ESP32）

| 文件 | 干什么 | 新手需要改吗 |
|------|--------|-------------|
| **boot.py** | 板子上电**第一个**跑。负责：读配置 → 连 WiFi → 连 MQTT → 判断要不要进配网模式（长按/复位按键检测）→ 最后启动 main.py | 不用改 |
| **main.py** | 主程序。死循环里：扫描按键 → 收 MQTT 下行命令 → 采一个 Modbus 点 → 上报数据。长按配网时写标记并重启 | 不用改 |
| **ap_config.py** | 配网模式：开 WiFi 热点 `RELAY-SETUP-xxxx`，手机连上后浏览器开 `192.168.4.1` 填配置。Day8 把 Modbus 配置做成了**可视化表单**（增删从站/采集点） | 不用改 |
| **app_config.py** | 读写板子上的 `config.json`（WiFi 密码、MQTT 地址、Modbus 从站列表），断电不丢 | 不用改 |
| **modbus_gw.py** | Modbus **主站**：主动连模拟器读寄存器（温湿度/人体/烟雾），时间片轮询不卡主循环。**Day8 新增数据飘动**：读到值后加点小随机扰动，让数据不死板 | 不用改 |
| **relay_hw.py** | 4 路继电器的 GPIO 控制 + 4 个按键扫描（短按切继电器、长按 5 秒进配网） | 不用改 |
| **config.json** | 当前生效的配置。本项目指向 Modbus 模拟器 `192.168.20.59:5502`，unit_id=7，采 4 个点 | 配网时网页改 |
| **umqtt/simple.py** | 第三方 MQTT 库，板子用它连 EMQX 发消息 | 不用改 |

### 电脑端（tools/，在电脑上用 Python 跑）

| 文件 | 干什么 | 什么时候跑 |
|------|--------|-----------|
| **gateway_bridge.py** | ⭐ **Day8 核心**。连 MQTT，订阅板子上报，按路由表拆成 7 个虚拟设备转发；同时订阅虚拟设备的控制命令，路由回板子 | **一直要跑** |
| **modbus_slave_sim.py** | Modbus **从站**模拟器，假装是温湿度/人体/烟雾传感器，提供寄存器给板子读。数据会自动飘动 | **一直要跑** |
| **set_modbus.py** | 一次性工具：手动往模拟器写传感器值（比如把温度基准设成 25°C） | 想改基准值时跑 |
| **detect_com.py** | 被 start_serial.bat 调用，自动找 ESP32 的 COM 口号 | 不用手动跑 |
| **start_all.bat** | ⭐ **双击它**：自动弹出两个窗口，分别跑模拟器和 Bridge | 每次演示先双击 |
| **start_serial.bat** | 双击后看板子串口日志（打印 WiFi/MQTT/Modbus 状态） | 调试板子时跑 |

## 运行步骤（从零开始，照着做）

### 准备工作（只需一次）

1. **装 Python 依赖**（电脑上）：
   ```powershell
   pip install pymodbus paho-mqtt pyserial esptool mpremote
   ```
2. **ESP32 板子已刷 Day8 固件并配好网**：
   - 板子能连上办公室 WiFi、连上 MQTT（`172.16.4.211:9783`）
   - 板子的 Modbus 配置指向模拟器（本项目是 `192.168.20.59:5502`，unit_id=7）
   - 如果板子还是旧固件/没配网，先看下面「附录：刷固件与配网」
3. **JetLinks 平台能登录**：`http://172.16.4.211`，账号 admin7

---

### 步骤 1：在 JetLinks 建 6 个虚拟产品

对下面 6 个产品，**每个都重复这套操作**（以门锁为例）：

1. 左侧菜单 **产品管理 → 新建产品**
   - 产品 ID：`lock-cc`（**必须和路由表一字不差**）
   - 产品名称：随便填（如"智能门锁"）
   - 设备类型：**直连设备**
   - 认证方式：**不认证**
2. 进入这个产品 → **物模型 → 新增属性**
   - 门锁/灯/空调：属性标识填 `switch`，类型 int，可读写
   - 温湿度产品：加两个属性 `temperature`、`humidity`，类型 **double（双精度浮点）**，只读
   - 人体产品：属性标识 `detected`，类型 int，只读
   - 烟雾产品：属性标识 `level`，类型 int，只读
3. **⚠️ 点页面上的「应用配置」按钮**（不点不生效！）
4. 产品页 → **设备 → 新增设备**，设备 ID 严格照路由表填：
   - lock-cc 下建 `lock001`
   - light-cc 下建 `light001` 和 `light002`（两个）
   - ac-cc 下建 `ac001`
   - sensor-cc 下建 `sensorcc`
   - human-cc 下建 `human001`
   - smoke-cc 下建 `smoke001`

> 建完后一共 6 个产品、7 个设备。设备 ID 和属性标识再对着上面路由表核对一遍。

---

### 步骤 2：启动电脑端两个程序

双击 **`tools/start_all.bat`**（或在 `day8/tools/` 目录下双击）。

会自动弹出**两个黑色 cmd 窗口**：

| 窗口标题 | 跑的命令 | 作用 |
|----------|---------|------|
| **ModbusSim** | `python -u modbus_slave_sim.py 5502 7` | 启动 Modbus 模拟器（端口 5502，unit_id=7） |
| **Bridge** | `python -u gateway_bridge.py` | 启动协议转换桥 |

**ModbusSim 窗口**正常应显示：
```
Modbus TCP 从站模拟器已启动: 0.0.0.0:5502 (unit_id=7)
寄存器布局:
  reg0  温度    (x10, 起始 25.3°C, 自动漂移)
  reg1  湿度    (x10, 起始 56.7%RH, 自动漂移)
  reg4  人体感应 (0=无人/1=有人, 每10秒随机切换)
  reg5  烟雾等级 (0~100, 自动波动, 偶尔飙升)
  ...
```

**Bridge 窗口**正常应显示：
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

> 💡 日志里 `light-cc (2 设备)` 的数字是**该产品下的设备数量**（light 有两个灯）。

> ⚠️ **模拟器跑在哪台机器？** 模拟器监听 `0.0.0.0:5502`，板子配网里的 Modbus IP 要填**跑模拟器这台机器的 IP**。本项目板子配的是实验室机器 `192.168.20.59`。如果你在自己电脑跑模拟器，就要把板子配网里的 Modbus IP 改成本机 IP。

---

### 步骤 3：确认板子在上报数据

双击 **`tools/start_serial.bat`**（输入 COM 号，板子是 COM5 就输 5，直接回车自动检测）。

板子正常时串口会持续打印：
```
[modbus] temperature = 29.6 (addr=0x0, type=uint16)
[modbus] humidity = 90.1 (addr=0x1, type=uint16)
[modbus] human = 1 (addr=0x4, type=uint16)
[modbus] smoke = 2 (addr=0x5, type=uint16)
```

数值一直在小范围变化 = **数据飘动生效**（这是 Day8 固件在板子端做的，不依赖模拟器版本）。

---

### 步骤 4：看 Bridge 转发 + JetLinks 数据

板子上报后，**Bridge 窗口**会打印转发日志：
```
  ↑ sensor-cc/sensorcc report: {'temperature': 29.6, 'humidity': 90.1}
  ↑ human-cc/human001 report: {'detected': 1}
  ↑ smoke-cc/smoke001 report: {'level': 2}
↑ 网关上报 8 个 key → 转发 7 个虚拟设备
```

然后去 **JetLinks 平台 → 设备管理**，逐个点开 7 个虚拟设备 → **运行状态**，应能看到：
- 温湿度 sensorcc：温度、湿度持续变化
- 人体 human001：detected 在 0/1 间变化
- 烟雾 smoke001：level 波动
- 门锁/灯/空调：switch 状态和板子继电器一致

---

### 步骤 5：测下行控制（平台点按钮 → 板子动）

在 JetLinks 上打开**门锁 lock001** 的设备详情 → 运行状态 → 编辑 `switch` 属性，改成 0 或 1（或用设备功能下发）。

- 板子上**继电器 1 会咔哒一声**切换
- **Bridge 窗口**打印回流日志：
  ```
  ↓ lock-cc/lock001 write {'switch': 0} → gateway {'relay1': 0}
  ```
- 灯 light001/light002、空调 ac001 同理，分别控制继电器 2/3/4

---

### （可选）手动改传感器基准值

在**能连到模拟器（192.168.20.59）**的电脑上，打开 cmd：
```powershell
cd day8\tools

# 位置参数: 温度 湿度 人体 烟雾
python set_modbus.py 25 60 1 50

# 或单独改某一个
python set_modbus.py --temp 30      # 温度基准 30.0°C
python set_modbus.py --humidity 80  # 湿度 80%RH
python set_modbus.py --human 0      # 人体: 0无人 / 1有人
python set_modbus.py --smoke 30     # 烟雾 0~100
```

写入后板子下次采集读到新基准，再围绕它飘动。

> 注意：飘动是围绕基准的**小幅波动，不会自己改基准**。想把温度从 30 拉回 25，就用上面命令写 reg0。

## Modbus 寄存器 / 采集点对照

模拟器 `modbus_slave_sim.py` 的寄存器布局，和板子 `config.json` 的采集配置一一对应：

| 寄存器 | 含义 | 板子 key | unit_id | scale | 采集周期 |
|--------|------|----------|---------|-------|---------|
| reg0 (0x0000) | 温度 ×10 | temperature | 7 | 0.1 | 3000ms |
| reg1 (0x0001) | 湿度 ×10 | humidity | 7 | 0.1 | 5000ms |
| reg4 (0x0004) | 人体 0/1 | human | 7 | 1 | 3000ms |
| reg5 (0x0005) | 烟雾 0~100 | smoke | 7 | 1 | 3000ms |

> ⚠️ unit_id 必须是 **7**、寄存器地址必须是 **0/1/4/5**。配错（比如 unit_id 写成 4、温度配成 reg3）板子读不到数据，平台上就是固定值或不更新。

## Day7 vs Day8 对比

| 对比项 | Day7 | Day8 |
|--------|------|------|
| 板子在平台上是几个设备 | 1 个（relaycc） | **物理 1 个 → 虚拟 7 个** |
| 平台产品数 | 1（relay-cc） | **6**（lock/light/ac/sensor/human/smoke） |
| 数据怎么上报 | 板子直接上报 | 板子上报 → **Bridge 拆分** → 7 个虚拟设备 |
| 控制怎么下发 | 平台直接控 relaycc | 平台控虚拟设备 → **Bridge 回流** → 板子继电器 |
| 传感器种类 | 温湿度 | 温湿度 + **人体 + 烟雾** |
| 数据飘动 | 只靠模拟器 | **板子端 + 模拟器双层飘动** |
| 配网 Modbus 配置 | 贴 JSON | **可视化表单**（增删从站/采集点） |
| 新增电脑端程序 | 无 | **gateway_bridge.py** |

## 验收清单

- [ ] JetLinks 建好 6 个产品、7 个设备，ID 全对，物模型都点了「应用配置」
- [ ] 双击 start_all.bat，ModbusSim 和 Bridge 两个窗口都正常启动
- [ ] Bridge 窗口打印"已连接"+ 订阅网关 + 订阅 6 个虚拟产品
- [ ] 板子串口持续打印 `[modbus] temperature/humidity/human/smoke = ...` 且数值在变
- [ ] Bridge 窗口打印 `↑ ... report: {...}` 转发日志
- [ ] JetLinks 上 7 个虚拟设备的属性都在更新（不是固定值/离线）
- [ ] 平台改门锁/灯/空调的 switch → 板子继电器咔哒 + Bridge 打印 `↓ ... → gateway {relayN: x}`
- [ ] `set_modbus.py 25 60 1 50` 能成功写入并看到新基准

## 故障排查

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| Bridge 窗口没"已连接" | MQTT 地址/网络不通 | 确认能连 `172.16.4.211:9783`，账号 test/123456 |
| Bridge 转发了，但 JetLinks 虚拟设备收不到/离线 | ① 虚拟产品 topic 缺前导 `/`；② 设备 ID/属性标识和路由表不一致 | ① Bridge 已自动加 `/`，别手改；② 严格照路由表核对 ID 和属性名 |
| 物模型改了不生效 | 没点「应用配置」 | 产品物模型每次改完点「应用配置」 |
| 温湿度/人体/烟雾是固定值 | ① 板子固件旧（没飘动逻辑）；② Modbus 配置 unit_id/地址错，读不到数据 | ① 刷 Day8 固件；② 核对 unit_id=7、reg0/1/4/5、模拟器 IP |
| 平台点开关，板子继电器没反应 | Bridge 没跑 / 下行 topic 没订阅 | 看 Bridge 窗口有没有打印 `↓ ... → gateway {...}`，没有就重启 Bridge |
| 板子串口打印 `connect fail 192.168.20.59:5502 ETIMEDOUT` | 模拟器没开 / 板子连不到那台机器 | 在 192.168.20.59 上启动模拟器；或把板子配网 Modbus IP 改成跑模拟器的机器 IP |
| 双击 start_all.bat 满屏乱码 | bat 编码问题 | 本项目 start_all.bat 已用纯英文+GBK，若被改坏重新从仓库拉取 |
| 长按 SW1 后进不了配网/热点开不出 | 旧固件运行中切 WiFi 模式会挂死 | Day8 固件已改为"长按→重启→进配网"；刷最新固件 |
| 手机连热点但网页打不开 | 手机没真正连热点 / 安卓切回 4G | 连 `RELAY-SETUP-xxxx`，安卓弹"无法访问互联网"点"保持连接"，浏览器开 `http://192.168.4.1` |

> 更多配网/刷机/串口相关的坑，见主仓库根目录 **README.md 第十一章「常见问题排查」**（11.7 配网页面打不开、11.9 Bridge 坑、11.10 刷机坑）。

## Day8 学了什么

- **网关 / 子设备架构**：一个物理网关如何在平台上呈现为多个逻辑设备（工业物联网常见模式）
- **协议转换桥（Bridge）模式**：上行按路由表拆分、下行按反向表回流，中间用消息 ID 映射把回复发回正确的设备
- **MQTT topic 设计**：网关 topic 不带前导 `/`，虚拟设备 topic 必须带 `/`（JetLinks 对第三方设备的要求）
- **数据飘动 / 模拟真实传感器**：为什么要在设备端叠加随机扰动，让演示数据可信
- **配置可视化**：把手写 JSON 改成表单，降低出错率
- **嵌入式稳定性**：运行中切 WiFi 模式会挂死 → 用"写标记 + 重启"在干净状态进配网

---

## 附录：刷固件与配网（板子是旧固件/没配网时才需要）

### A.1 擦除 + 刷 MicroPython 解释器

> ⚠️ 先关掉所有串口监控窗口（COM 口同一时刻只能被一个程序占用）。

```powershell
cd day8\esp32_firmware

# 1. 擦除整块 flash
python -m esptool --port COM5 --chip esp32c3 erase-flash

# 2. 刷 MicroPython 解释器
python -m esptool --port COM5 --chip esp32c3 --baud 460800 write-flash 0x0 _firmware\ESP32_GENERIC_C3-v1.29.0.bin
```

### A.2 上传固件源码

```powershell
cd day8\esp32_firmware

# 建 umqtt 目录并传库
python -m mpremote connect COM5 fs mkdir umqtt
python -m mpremote connect COM5 fs cp umqtt\__init__.py :/umqtt/__init__.py
python -m mpremote connect COM5 fs cp umqtt\simple.py :/umqtt/simple.py

# 传核心文件（目标路径用正斜杠 /）
python -m mpremote connect COM5 fs cp boot.py :/boot.py
python -m mpremote connect COM5 fs cp main.py :/main.py
python -m mpremote connect COM5 fs cp ap_config.py :/ap_config.py
python -m mpremote connect COM5 fs cp app_config.py :/app_config.py
python -m mpremote connect COM5 fs cp modbus_gw.py :/modbus_gw.py
python -m mpremote connect COM5 fs cp relay_hw.py :/relay_hw.py
python -m mpremote connect COM5 fs cp config.json :/config.json
```

> 提示：板子在跑 main.py 死循环时 mpremote 可能进不去，先做 A.1 的 erase-flash 再传。
> 如果 `cp` 提示 "Up to date" 但没更新，先 `python -m mpremote connect COM5 fs rm main.py` 删了再传。

### A.3 配网

1. **进入配网模式**（二选一）：
   - 正常运行时**长按 SW1 约 6 秒**松开 → 板子自动重启进配网
   - 或按住任意按键再按板子 RST 复位键
2. 手机/电脑连 WiFi 热点 **`RELAY-SETUP-xxxx`**（开放无密码）
3. 安卓弹"无法访问互联网"→ 点**保持连接/仍要连接**
4. 浏览器打开 **`http://192.168.4.1`**
5. 填 WiFi、MQTT（`172.16.4.211:9783`，test/123456，产品 relay-cc，设备 relaycc）
6. Modbus 表单填：从站 IP `192.168.20.59`、端口 `5502`、单元 ID `7`，加 4 个采集点（reg0 temperature、reg1 humidity、reg4 human、reg5 smoke）
7. 点**保存并应用** → 板子重启回正常运行
