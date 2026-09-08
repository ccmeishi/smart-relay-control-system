"""探测实训 Modbus 从站的 unit_id 和可用寄存器范围"""
from pymodbus.client import ModbusTcpClient

HOST = "192.168.20.59"
PORT = 5502

def scan_unit(uid):
    """扫描某个 unit_id 下的寄存器"""
    c = ModbusTcpClient(HOST, port=PORT)
    if not c.connect():
        return None
    found = []
    for start in range(0, 20, 1):
        try:
            rr = c.read_holding_registers(start, count=1, slave=uid)
            if not rr.isError():
                found.append((start, rr.registers[0]))
        except Exception:
            pass
    c.close()
    return found

print(f"=== 扫描 {HOST}:{PORT} ===")
for uid in range(1, 10):
    regs = scan_unit(uid)
    if regs:
        print(f"\nunit_id={uid}: {len(regs)} 个寄存器")
        for addr, val in regs:
            print(f"  reg{addr} = {val}")
    else:
        print(f"\nunit_id={uid}: 无响应")
