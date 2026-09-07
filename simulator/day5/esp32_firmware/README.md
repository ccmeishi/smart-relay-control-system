# Day5: ESP32 继电器固件（核心里程碑）

## 当天目标
用 MicroPython 给 ESP32-C3 开发板写完整固件，替代 PC 模拟器。

## 新增文件清单

| 文件 | 说明 |
|------|------|
| `boot.py` | 启动入口，预连 WiFi |
| `main.py` | 主循环 + MQTT + 配网切换 |
| `app_config.py` | config.json 读写 + 原子写 |
| `ap_config.py` | AP 热点 + HTTP 配网页 |
| `relay_hw.py` | GPIO 控制 + Timer 按键扫描 |
| `config.py` | 早期硬编码配置（已被 app_config 替代） |
| `umqtt/simple.py` | MicroPython MQTT 库 |
| `_firmware/ESP32_GENERIC_C3-v1.29.0.bin` | MicroPython 解释器 |

## 核心功能

- ✅ 4 路继电器 GPIO 控制（GPIO 3/4/5/7，高电平触发）
- ✅ SW1~SW4 按键扫描（Timer 每 50ms 扫一次）
- ✅ SW1 长按 6 秒触发 AP 配网模式
- ✅ MQTT 直连 JetLinks（断线指数退避重连 5→10→20→40→60s）
- ✅ 持久化配置 `/config.json`（原子写防掉电损坏）
- ✅ properties/report + function/invoke/reply 完整实现

## 与 Day2 对比

| 对比项 | Day2 (PC 模拟器) | Day5 (ESP32 固件) |
|--------|-----------------|-------------------|
| 运行位置 | PC 上跑 Python | ESP32 板子上跑 MicroPython |
| 继电器 | 模拟 8 路 | 实物 4 路 |
| 控制方式 | MQTT | 本地按键 + MQTT |
| 配置 | config_relay.json（手动改） | 配网页面（SW1 长按触发） |
| 依赖 | pymodbus + paho-mqtt | 零外部依赖（MicroPython 内置） |

## 运行指令

### 烧录固件

```powershell
# 擦除
python -m esptool --port COM5 erase_flash
# 烧录 MicroPython
python -m esptool --port COM5 --chip esp32c3 flash_mode dio --flash_freq 40m flash_id _firmware/ESP32_GENERIC_C3-v1.29.0.bin
# 上传源码
python -m mpremote connect COM5 cp boot.py :/boot.py
python -m mpremote connect COM5 cp app_config.py :/app_config.py
python -m mpremote connect COM5 cp relay_hw.py :/relay_hw.py
python -m mpremote connect COM5 cp ap_config.py :/ap_config.py
python -m mpremote connect COM5 cp main.py :/main.py
# umqtt 库
python -m mpremote connect COM5 mkdir umqtt
python -m mpremote connect COM5 cp umqtt/simple.py :umqtt/simple.py
```

### 串口监控

```powershell
python -c "import serial,time; s=serial.Serial('COM5',115200,timeout=1); time.sleep(2); print(s.read(s.in_waiting or 4096).decode('utf-8','replace')); s.close()"
```

### 配网

1. 板子首次开机（或清空 config.json）自动进配网
2. 正常运行时长按 SW1 6 秒进配网
3. 手机连热点 `RELAY-SETUP-xxxx` → 浏览器开 http://192.168.4.1
4. 填 WiFi + MQTT + 产品/设备 ID → 保存重启
