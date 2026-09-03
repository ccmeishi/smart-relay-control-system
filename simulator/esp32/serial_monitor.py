"""临时工具: 复位 ESP32 并打印串口启动日志

用法: python serial_monitor.py [COM口] [秒数]
默认: COM5, 25 秒
"""
import sys
import time

import serial

PORT = sys.argv[1] if len(sys.argv) > 1 else "COM5"
SECONDS = float(sys.argv[2]) if len(sys.argv) > 2 else 25

s = serial.Serial(PORT, 115200, timeout=0.5)
s.setDTR(False)
s.setRTS(True)          # RTS 拉低复位
time.sleep(0.1)
s.setRTS(False)         # 释放复位, 开始启动

t0 = time.time()
while time.time() - t0 < SECONDS:
    data = s.readline()
    if data:
        print(data.decode("utf-8", "replace").rstrip())
