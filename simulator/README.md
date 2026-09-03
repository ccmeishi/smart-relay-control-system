# simulator · 程序说明与操作步骤指南

本目录包含全部设备模拟器、实物固件与辅助工具。**每个程序是什么、怎么启动、三种运行场景如何搭配**，看这一份文档即可。

---

## 一、程序对照表

### day1/ — 温湿度传感器（原始报文版，阶段 1）

| 文件 | 说明 |
|---|---|
| `sensor_simulator.py` | 温湿度传感器模拟器：5 秒轮询 Modbus → 变化才上报原始报文到 `device/sensor/sevengroup`（需配合 EMQX 规则引擎转换后才能进 JetLinks） |
| `config.json` | Modbus 地址、MQTT broker、上报主题等配置 |
| `requirements.txt` | day1 依赖（pymodbus 3.6.9 / paho-mqtt 1.6.1） |

### day2/ — JetLinks 直连版模拟器 + Web 控制台（阶段 2）

| 文件 | 说明 |
|---|---|
| `sensor_simulator_jl.py` | 温湿度传感器模拟器（JetLinks 官方 MQTT 协议直连，上报 `temperature`/`humidity`，支持 set_temperature / set_humidity / set_both 功能调用与属性写入/读取响应） |
| `relay_simulator_jl.py` | 8 路继电器模拟器（JetLinks 直连，桥接平台与 Modbus 从站：读 reg2~9 → 上报 relay1~8；收到控制命令 → 写寄存器 → 回 reply → 主动上报新状态） |
| `relay_ui.py` | **继电器 Web 控制台**（浏览器打开 http://127.0.0.1:8081 ），两种模式可切换：<br>• **MQTT 链路模式**：走 平台→EMQX→模拟器→Modbus 完整链路，带实时报文日志<br>• **直连 Modbus 模式**：直接读写 Modbus 从站寄存器（不产生平台报文，用于本地调试/实物控制） |
| `config_relay.json` | 继电器模拟器/UI 的配置（Modbus 从站地址、MQTT、product_id/device_id、寄存器映射） |
| `config_jetlinks.json` | 温湿度模拟器配置 |
| `start_relay.bat` / `start_sensor.bat` / `start_ui.bat` | Windows 一键启动脚本（双击即运行对应程序） |
| `emqx_rule.sql` | 方式一（EMQX 规则引擎）的 SQL 与动作配置说明 |
| `test_format_compare.py` | 两种上报格式（原始报文 vs JetLinks 标准）对比测试 |
| `requirements.txt` | day2 依赖（含 flask 3.0.3） |

### esp32/ — 实物测试固件（阶段 3，ESP32-C3 四路继电器板）

| 文件 | 说明 |
|---|---|
| `boot.py` | 上电自动连接 WiFi |
| `config.py` | 全局配置：WiFi 账号、MQTT（EMQX）、继电器 GPIO 与触发电平、Modbus 端口/unit_id |
| `relay_hw.py` | GPIO 抽象层：逻辑 0/1 ↔ 电平换算（`RELAY_ACTIVE_LOW` 控制触发电平），两条路线共用 |
| `main_mqtt.py` | **路线 A**：板子作为 MQTT 设备直连 EMQX，按 JetLinks 协议上报 relay1~4 并响应平台控制 |
| `main_modbus.py` | **路线 B**：板子作为 Modbus TCP **从站**（端口 502，unit_id=7），寄存器布局与实验室从站一致，PC 端可直接读写控制继电器 |
| `serial_monitor.py` | 串口日志工具（查看板子运行输出） |
| `umqtt/simple.py` | MicroPython 官方 MQTT 库 |
| `_firmware/ESP32_GENERIC_C3-v1.29.0.bin` | MicroPython v1.29 固件（烧录用） |

### tools/ — 辅助工具

| 文件 | 说明 |
|---|---|
| `modbus_slave_sim.py` | 本地 Modbus TCP 从站模拟器（127.0.0.1:5502，unit_id=7，reg0 温度×10 / reg1 湿度×10 / reg2~9 继电器，电流电压联动）。**用本地从站测试时必须第一个启动** |
| `modbus_scan.py` | 从站寄存器扫描工具（扫描 unit_id 与寄存器范围，用于排查 IllegalAddress） |
| `diag_*.py` | MQTT/平台链路诊断脚本（回环测试、订阅监听、下发触发等，排查"平台没数据"时用） |
| `start_slave.bat` | 一键启动本地从站模拟器 |

---

## 二、三种运行场景操作步骤

> 公共前提：`pip install -r day1/requirements.txt -r day2/requirements.txt`
> MQTT 服务器：172.16.4.211:9783（账号 test / 123456），各程序 client_id 已互不相同，可同时在线。

### 场景一：本地自测（不依赖老师服务器，验证程序逻辑）

```powershell
# 1. 先启动本地从站（必须第一个启动）
python tools\modbus_slave_sim.py

# 2. 新开窗口，启动继电器模拟器（config_relay.json 的 modbus.host 改为 127.0.0.1, port 5502）
python day2\relay_simulator_jl.py

# 3. 新开窗口，启动温湿度模拟器（config_jetlinks.json 同样指向 127.0.0.1）
python day2\sensor_simulator_jl.py
```

- 从站窗口会实时打印继电器操作记录（🔔 标记）；继电器窗口变化时才上报（安静是正常的）。

### 场景二：完整平台链路（实验室标准玩法，数据进 JetLinks）

```powershell
# 1. 确认配置指向实验室环境：
#    day2/config_relay.json    -> modbus.host = 192.168.20.59, port 5502 (实训从站)
#                                 mqtt.host = 172.16.4.211, port 9783
#    day2/config_jetlinks.json -> 同上
# 2. 双击 start_relay.bat + start_sensor.bat（或命令行运行）
# 3. 双击 start_ui.bat，浏览器打开 http://127.0.0.1:8081
#    - MQTT 链路模式：在网页上点开关 = 走平台完整链路控制，右侧实时显示报文
#    - 也可直接在 JetLinks 平台设备详情页操作（编辑属性/功能调用）
# 4. 温湿度数据在 JetLinks 平台 "温湿度传感器-CC / sensorcc" 设备详情查看
```

- 8 路继电器（relay1~8）对应实训从站 reg2~9；总电流/电源电压为联动计算值。
- 若平台显示在线但收不到数据：平台设备详情页点「断开连接」清掉僵死会话，再重启模拟器。

### 场景三：实物测试（ESP32 四路继电器板）

**烧录（只需做一次）**：

```powershell
cd simulator\esp32
# 1. 烧录 MicroPython 固件 (COM5 按实际端口改)
python -m esptool --port COM5 erase_flash
python -m esptool --port COM5 write_flash 0x0 _firmware\ESP32_GENERIC_C3-v1.29.0.bin
# 2. 上传代码 (路线A/B 都要传这些)
python -m mpremote cp config.py relay_hw.py boot.py umqtt/simple.py :/
```

**路线 B（推荐先测）：板子 = Modbus 从站，PC 端无缝替换"从站"**

```powershell
# 1. 上传路线B固件为 main.py 并重启
python -m mpremote cp main_modbus.py :/main.py
python -m mpremote reset
#    串口会打印板子 IP（如 192.168.30.145）

# 2. PC 端 day2/config_relay.json 改为: "host": "<板子IP>", "port": 502
#    (unit_id=7, register_start=2, register_count=8 保持不变)

# 3. 双击 start_ui.bat -> 页面切到「直连 Modbus 模式」
#    点继电器 1~4 -> 板子对应继电器咔哒吸合/断开、指示灯亮灭
#    (PC 端 relay_simulator_jl.py 可同时运行, 把实物状态照常上报到平台)
```

**路线 A：板子 = MQTT 设备直连平台（脱离 PC 独立上报）**

```powershell
# 1. 上传路线A固件为 main.py 并重启
python -m mpremote cp main_mqtt.py :/main.py
python -m mpremote reset

# 2. 必须关闭 PC 端 relay_simulator_jl.py（client_id 不同但 deviceId 相同，
#    双上报会导致平台会话错乱）
# 3. JetLinks 平台 relaycc 设备详情：属性 relay1~4 正常显示，编辑属性即可控制实物
```

---

## 三、配置速查

| 运行环境 | Modbus 从站地址 | port | unit_id | 说明 |
|---|---|---|---|---|
| 本地自测 | 127.0.0.1 | 5502 | 7 | 从站 = `tools/modbus_slave_sim.py` |
| 实验室实训从站 | 192.168.20.59 | 5502 | 7 | 从站 = 实训教室设备 |
| ESP32 实物（路线B） | 192.168.30.145（以串口打印为准） | 502 | 7 | 从站 = 板子本身 |

- MQTT 一律 `172.16.4.211:9783`（test/123456）；上报 topic `/relay-cc/relaycc/properties/report`、`/sensor-cc/sensorcc/properties/report`。
- 继电器板为**高电平触发**（`config.py` 中 `RELAY_ACTIVE_LOW = False`）；若换板后出现"上电全亮/UI开=灭"，改这个开关即可。

## 四、常见问题

| 现象 | 处理 |
|---|---|
| 平台显示在线但收不到新数据 | 平台设备详情页点「断开连接」清僵死会话 → 重启模拟器 |
| 模拟器连从站报 IllegalAddress | 从站只有 reg0~9，检查 `register_start=2 / register_count=8`；用 `tools/modbus_scan.py` 扫描确认 |
| 控制无反应 | 确认从站存活、确认只有一个模拟器实例在跑（避免 client_id 冲突互踢） |
| 值莫名变化 | 实训从站是共享的，可能被其他小组写入；本地复现用 `modbus_slave_sim.py` |
| 实物上电全亮 | 触发电平配反了，改 `config.py` 的 `RELAY_ACTIVE_LOW` |
| taskkill 杀进程 | 不要 `taskkill /IM python.exe`（会误杀从站），用窗口标题过滤或直接关窗口 |
