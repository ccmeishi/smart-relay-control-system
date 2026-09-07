# Day5 · ESP32 固件移植（继电器控制）

## 当天目标

把 Day2 PC 上跑的继电器控制逻辑**移植到 ESP32-C3 实物**上跑起来。这是第一次真正摸到硬件——前面几天全在 PC 模拟器里。移植完 ESP32 就具备：
- WiFi 连接 + AP 配网
- 4 路继电器 GPIO 控制
- 按钮手动控制
- MQTT 直连 JetLinks（双向命令）

## 架构对比

```
Day2 (PC 模拟器)                         Day5 (ESP32 实物)
┌──────────────────┐                    ┌───────────────────────────┐
│ relay_simulator  │ 读 Modbus reg2~5    │ ESP32-C3 (GPIO 3,4,5,7)  │
│ _jl.py           │──────────────────▶ │  relay_hw.py → 直接操作  │
│                  │ 写 Modbus reg2~5    │  GPIO HIGH/LOW           │
└──────────────────┘                    └───────────────┬───────────┘
                                                        │
                                         JetLinks MQTT 双向通信
```

## ESP32-C3 硬件

| 项目 | 值 |
|------|-----|
| 芯片 | ESP32-C3-MINI-1 |
| Flash | 4MB |
| 继电器板 | 4 路继电器开发板 |
| 继电器 GPIO | GPIO 3, 4, 5, 7（HIGH 触发） |
| 按钮 GPIO | SW1=IO10, SW2=IO9, SW3=IO6, SW4=IO8 |
| 通信 | WiFi + MQTT |
| USB 转串口 | CP210x |

## 代码结构

```
day5/
├── esp32_firmware/          ← ESP32 固件源码（完整快照）
│   ├── _firmware/
│   │   └── ESP32_GENERIC_C3-v1.29.0.bin   ← MicroPython 解释器
│   ├── umqtt/
│   │   └── simple.py                       ← MicroPython umqtt 库
│   ├── boot.py                             ← 开机先跑（静默）
│   ├── main.py                             ← 主程序入口
│   ├── app_config.py                       ← WiFi/MQTT 配置（AP 配网存这里）
│   ├── ap_config.py                        ← AP 配网 HTTP 服务器
│   ├── relay_hw.py                         ← 继电器硬件驱动
│   ├── config.py                           ← JetLinks 产品/设备 ID
│   └── README.md                           ← 固件内嵌说明
├── flash_and_upload.bat     ← 🆕 全流程一键：擦除→烧录→上传→监控
├── upload_only.bat          ← 🆕 仅上传源码（板子已有 MicroPython 时用）
└── README.md                ← 本文件
```

### 6 个固件文件的职责

| 文件 | 职责 | 是否改硬件 |
|------|------|-----------|
| `boot.py` | 空文件（MicroPython 要求存在但内容可空） | - |
| `main.py` | 主循环：WiFi→MQTT→继电器初始化→MQTT 消息回调 | 否 |
| `app_config.py` | 配置 JSON 文件读写（WiFi SSID/密码, MQTT 参数） | 否 |
| `ap_config.py` | AP 配网模式：建临时 WiFi + HTTP 页面让用户填配置 | 否 |
| `relay_hw.py` | 4 路继电器 GPIO + 4 路按钮初始化 + 读写 | **是** |
| `config.py` | JetLinks productId / deviceId （`relay-cc` / `relaycc`） | 否 |

### main.py 启动流程

```python
def main():
    1. relay_hw.init()              # 初始化 GPIO（继电器+按钮）
    2. cfg = app_config.load()      # 加载 WiFi/MQTT 配置
    3. sta_if.connect(...)          # 连 WiFi
       ├── 3a. 失败 → ap_config.run()  # 开 AP 配网模式（阻塞）
       └── 3b. 成功 → 继续
    4. MQTTClient.connect()        # 连 JetLinks MQTT
       注册 set_relay 命令回调
    5. 主循环 while True:
       ├── mqtt.check_msg()        # 收下行命令
       ├── 按钮检测                # 手动控制继电器
       ├── 周期上报 relay 状态    # MQTT → properties/report
       └── 喂狗 / 延时
```

### 按钮长按进入 AP 配网

```python
# SW1 (IO10) 长按 ~6 秒
# 触发 ap_config.run() → 开 AP → 用户通过 192.168.4.1 填 WiFi 密码
```

## 运行步骤

### 准备工作

1. 安装 USB 驱动：CP210x（ESP32-C3 模块自带）
2. Python 依赖：
   ```powershell
   pip install esptool mpremote pyserial
   ```
3. 用 USB 线连接 ESP32-C3 开发板
4. 设备管理器确认 COM 口（如 COM5）

### 方式 1：全流程一键（推荐首次烧录）

```
双击 flash_and_upload.bat
```

脚本自动完成：
1. 擦除旧固件
2. 烧录 MicroPython v1.29.0
3. 上传全部 .py 源码
4. 打印开机日志（验证 WiFi/MQTT 连接）

### 方式 2：仅上传源码（板子已有 MicroPython）

代码改了想快速更新，跳过擦除和烧录：

```
双击 upload_only.bat
```

### 方式 3：手动命令

```powershell
# 烧录 MicroPython（首次）
python -m esptool --port COM5 erase_flash
python -m esptool --port COM5 --chip esp32c3 flash_mode dio --flash_freq 40m flash_id esp32_firmware\_firmware\ESP32_GENERIC_C3-v1.29.0.bin

# 上传源码
python -m mpremote connect COM5 cp esp32_firmware\boot.py :/boot.py
python -m mpremote connect COM5 cp esp32_firmware\app_config.py :/app_config.py
python -m mpremote connect COM5 cp esp32_firmware\relay_hw.py :/relay_hw.py
python -m mpremote connect COM5 cp esp32_firmware\ap_config.py :/ap_config.py
python -m mpremote connect COM5 cp esp32_firmware\config.py :/config.py
python -m mpremote connect COM5 cp esp32_firmware\main.py :/main.py
python -m mpremote connect COM5 mkdir umqtt
python -m mpremote connect COM5 cp esp32_firmware\umqtt\simple.py :umqtt\simple.py

# 重启
python -m mpremote connect COM5 reset
```

### 串口监控

```
双击 simulator/esp32/start_serial.bat
```

或手动：
```powershell
python -m serial.tools.miniterm COM5 115200 --rts 0 --dtr 0
```

### 预期开机日志

```
[boot] MicroPython v1.29.0 on 2026-09-02; ESP32-C3
[main] 继电器硬件初始化: 4 路 (GPIO 3,4,5,7)
[main] 按钮初始化: SW1=IO10, SW2=IO9, SW3=IO6, SW4=IO8
[main] 连接 Office-WiFi ...
[main] WiFi OK: 192.168.30.145
[main] MQTT 连接 172.16.4.211:9783 (user=test)
[main] MQTT 已连接 ✅
[main] 订阅: /relay-cc/relaycc/function/invoke
[main] 进入主循环...
```

### 串口日志里没看到这些？

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| 直接进 REPL `>>>` | main.py 上传失败 | 重传 main.py |
| 反复打印 WiFi 重试 | WiFi SSID/密码错 | 长按 SW1 进入 AP 配网模式 |
| 连了 WiFi 但 MQTT 失败 | Broker 不可达 | 检查 PC 能不能 ping 172.16.4.211 |
| 串口输出乱码 | 波特率不对 | 设 115200 |

## JetLinks 远程控制测试

MQTTX 客户端发送：
```
Topic: /relay-cc/relaycc/function/invoke
Payload: {"messageId":"t1","functionId":"set_relay","inputs":{"继电器编号":1,"状态":0}}
```

ESP32 应回复：
```
Topic: /relay-cc/relaycc/function/invoke/reply
Payload: {"messageId":"t1","success":true,...}
```

继电器 1 应实际吸合/断开。

## 注意事项

### mpremote exec 会中断 main.py

每次用 `python -m mpremote connect COM5 exec "..."` 都会让板子卡进 REPL，main.py 停止运行（按钮也不响应）。**exec 完一定要 reset 板子**。

### 长按 SW1 没反应？

板子必须处于**正常运行状态**（main.py 已经跑起来，串口日志能看到 `[main] 进入主循环`），长按才生效。如果板子卡进了 AP 模式或者 REPL，长按是没用的。

### .trae/ 不是固件内容

`simulator/esp32/.trae/` 是 TRAE IDE 配置目录，**不会上传到板子，也不该 commit**。.gitignore 已配置。

## Day5 学了什么

- MicroPython 固件开发 vs PC Python 的差异（内存受限、API 子集、异步模型）
- ESP32-C3 GPIO 控制 + 按钮中断
- WiFi STA + AP 双模式切换
- MQTT 双向通信在嵌入式上的实现
- 固件更新流程：esptool 烧 MicroPython + mpremote 上传源码

## 与 Day7 的关系

Day7 在 Day5 固件基础上新增 `modbus_gw.py`，让 ESP32 既能控制继电器（本地 GPIO），又能当 Modbus 网关读 Day1 温湿度（远程 TCP）。文件变化：

| Day5 | Day7 变化 |
|------|----------|
| - | 🆕 `modbus_gw.py`（Modbus TCP 主站） |
| `main.py` | 修改：插入 `modbus_gw.poll_one()` |
| `app_config.py` | 修改：新增 `modbus_enabled` / `modbus_slaves` |
| `ap_config.py` | 修改：HTML 表单新增 Modbus 配置 |
| `relay_hw.py` | **不变** |
| `config.py` | **不变** |
| `boot.py` | **不变** |
