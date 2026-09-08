"""修改 Modbus 模拟器的传感器值

用法:
  python set_modbus.py 25 60                # 温度 25.0°C, 湿度 60.0%RH
  python set_modbus.py 25 60 1 50           # 温度25, 湿度60, 人体有人, 烟雾50
  python set_modbus.py --temp 30            # 只改温度
  python set_modbus.py --humidity 80        # 只改湿度
  python set_modbus.py --human 1            # 只改人体(1=有人,0=无人)
  python set_modbus.py --smoke 30           # 只改烟雾等级(0~100)
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
    return len(resp) == 12 and resp[7] == 0x06


def main():
    args = sys.argv[1:]
    if not args:
        print("用法:")
        print("  python set_modbus.py <温度> [湿度] [人体] [烟雾]")
        print("  python set_modbus.py --temp 30 --humidity 80 --human 1 --smoke 50")
        sys.exit(1)

    # 解析参数: 支持位置参数和命名参数
    temp = humidity = human = smoke = None
    positional = []
    i = 0
    while i < len(args):
        if args[i] == "--temp":
            temp = float(args[i + 1]); i += 2
        elif args[i] == "--humidity":
            humidity = float(args[i + 1]); i += 2
        elif args[i] == "--human":
            human = int(args[i + 1]); i += 2
        elif args[i] == "--smoke":
            smoke = int(args[i + 1]); i += 2
        else:
            positional.append(args[i]); i += 1

    if positional:
        if len(positional) >= 1: temp = float(positional[0])
        if len(positional) >= 2: humidity = float(positional[1])
        if len(positional) >= 3: human = int(positional[2])
        if len(positional) >= 4: smoke = int(positional[3])

    if temp is not None:
        reg0 = int(round(temp * 10))
        if write_register(0, reg0):
            print(f"✅ 温度 reg0 = {reg0}  →  {temp:.1f}°C")
        else:
            print(f"❌ 温度写入失败")

    if humidity is not None:
        reg1 = int(round(humidity * 10))
        if write_register(1, reg1):
            print(f"✅ 湿度 reg1 = {reg1}  →  {humidity:.1f}%RH")
        else:
            print(f"❌ 湿度写入失败")

    if human is not None:
        reg4 = 1 if human else 0
        if write_register(4, reg4):
            print(f"✅ 人体感应 reg4 = {reg4}  →  {'有人' if reg4 else '无人'}")
        else:
            print(f"❌ 人体感应写入失败")

    if smoke is not None:
        reg5 = max(0, min(100, int(smoke)))
        if write_register(5, reg5):
            print(f"✅ 烟雾等级 reg5 = {reg5}")
        else:
            print(f"❌ 烟雾等级写入失败")


if __name__ == "__main__":
    main()
