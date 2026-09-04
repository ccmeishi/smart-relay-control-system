"""boot.py - MicroPython 上电最先执行

Day5 统一固件 (main.py) 自己管理 WiFi(STA/AP) 与 MQTT,
这里不再自动连 WiFi, 只打印启动横幅, 避免未配网时白等 40 秒。
旧路线固件 (main_modbus.py) 会自行连接 config.py 里的 WiFi。
"""
import time
import network

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
try:
    import ubinascii
    mac = ubinascii.hexlify(wlan.config("mac")).decode()
    print("boot: ESP32 启动, MAC =", mac)
except Exception:
    print("boot: ESP32 启动")
time.sleep_ms(100)
