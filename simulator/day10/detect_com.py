"""检测 ESP32 COM 口，输出纯数字编号（如 "5" 或空）"""
import serial.tools.list_ports
ports = serial.tools.list_ports.comports()

# 匹配 ESP32 / 常见 USB-TTL 芯片的 VID:PID
TARGET_CHIPS = {
    (0x303a, 0x1001),  # ESP32-C3 原厂 USB CDC
    (0x10c4, 0xa604),  # Silicon Labs CP210x
    (0x1a86, 0x7523),  # WCH CH340 / CH341
    (0x0403, 0x6001),  # FTDI FT232
}

# 优先匹配目标芯片
for p in ports:
    vid_pid = (p.vid, p.pid) if p.vid and p.pid else None
    if vid_pid and vid_pid in TARGET_CHIPS:
        num = ''.join(c for c in p.device if c.isdigit())
        if num:
            print(num)
            break
else:
    # 没有匹配到 VID:PID，用 desc 里不含 "蓝牙" 的 COM 口兜底
    for p in ports:
        if p.device.startswith('COM') and '蓝牙' not in (p.description or ''):
            num = ''.join(c for c in p.device if c.isdigit())
            if num:
                print(num)
                break
