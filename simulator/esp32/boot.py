"""boot.py - MicroPython 上电最先执行: 先把 WiFi 连上

两条路线 (main_mqtt.py / main_modbus.py) 都依赖网络。
WiFi 连不上会打印失败, main 里会再重试。
"""
import time
import network
import config as C

wlan = network.WLAN(network.STA_IF)
wlan.active(True)

if not wlan.isconnected():
    print("boot: 连接WiFi", C.WIFI_SSID)
    wlan.connect(C.WIFI_SSID, C.WIFI_PASS)
    for _ in range(200):                    # 最长等 40s
        time.sleep_ms(200)
        if wlan.isconnected():
            break

if wlan.isconnected():
    print("boot: WiFi OK, IP =", wlan.ifconfig()[0])
else:
    print("boot: WiFi 连接失败, 稍后由 main 重试")
