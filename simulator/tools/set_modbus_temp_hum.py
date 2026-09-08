"""修改 Modbus 模拟器的温湿度值

用法:
  python set_modbus_temp_hum.py 25 60       # 温度 25.0°C, 湿度 60.0%RH
  python set_modbus_temp_hum.py 30          # 只改温度 30.0°C
  python set_modbus_temp_hum.py --humidity 80  # 只改湿度 80.0%RH
"""

import socket
import struct
import sys

MODBUS_IP = "192.168.20.59"
MODBUS_PORT = 5502
UNIT_ID = 7


def write_register(addr, val):
    """用功能码 0x06 写单个寄存器"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(5)
    s.connect((MODBUS_IP, MODBUS_PORT))
    tid = 1
    pdu = struct.pack(">BHH", 0x06, addr, val)
    frame = struct.pack(">HHHB", tid, 0, len(pdu) + 1, UNIT_ID) + pdu
    s.sendall(frame)
    resp = s.recv(12)
    s.close()
    ok = (len(resp) == 12 and resp[7] == 0x06)
    return ok


def main():
    if len(sys.argv) < 2:
        print("用法: python set_modbus_temp_hum.py <温度> [湿度]")
        print("  例: python set_modbus_temp_hum.py 25 60  (25.0°C, 60.0%RH)")
        sys.exit(1)

    temp = float(sys.argv[1])
    humidity = float(sys.argv[2]) if len(sys.argv) > 2 else None

    # 温度 → reg0 (x10)
    reg0 = int(round(temp * 10))
    if write_register(0, reg0):
        print(f"✅ 温度 reg0 = {reg0}  →  {temp:.1f}°C")
    else:
        print(f"❌ 温度写入失败")

    # 湿度 → reg1 (x10)
    if humidity is not None:
        reg1 = int(round(humidity * 10))
        if write_register(1, reg1):
            print(f"✅ 湿度 reg1 = {reg1}  →  {humidity:.1f}%RH")
        else:
            print(f"❌ 湿度写入失败")


if __name__ == "__main__":
    main()
