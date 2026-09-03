"""Modbus TCP 从站模拟器(联调测试用)

作用: 在没有实验室从站的环境里, 本机模拟一台 8 通道继电器从站.
  - 支持 8 路继电器 (reg2~reg9)
  - 电流自动联动 (每开一路 +0.5A)
  - 电压微小波动 (218V~222V)
  - slave ID 可通过命令行参数指定 (默认 9)

寄存器布局 (unit_id 可配置):
  reg0  = 温度 x10 (起始 253 => 25.3 C)
  reg1  = 湿度 x10 (起始 567 => 56.7 %RH)
  reg2~reg9 = 继电器1~8 (0=关/1=开)
  reg10 = 总电流 x10(A)  (每开一路 +0.5A)
  reg11 = 电源电压 x10(V) (218~222V 波动)
  reg12~reg15 = 预留

支持功能码: 0x03 读保持寄存器 / 0x06 写单个寄存器

用法:
  python modbus_slave_sim.py                  # 默认 unit_id=9, 端口 5502
  python modbus_slave_sim.py 5503             # 指定端口
  python modbus_slave_sim.py 5502 9           # 指定端口和 unit_id
"""

import random
import socketserver
import struct
import sys
import threading
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5502
UNIT_ID = int(sys.argv[2]) if len(sys.argv) > 2 else 7

# 寄存器布局 (共 16 个保持寄存器)
REGS = [253, 567, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2200, 0, 0, 0, 0]
LOCK = threading.Lock()
RELAY_REGS = [2, 3, 4, 5, 6, 7, 8, 9]   # 8 路继电器对应寄存器偏移
CURRENT_REG = 10
VOLTAGE_REG = 11
RELAY_COUNT = 8


def relay_state(regs, offset):
    return "开 ⚡" if regs[offset] else "关 ⚪"


def recalc_current():
    """根据当前继电器开关数量重算总电流"""
    count = sum(1 for i in RELAY_REGS if REGS[i])
    return count * 5   # 每开一个继电器 = 0.5A, 存寄存器值是 x10, 所以 0.5*10=5


def recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("对端断开")
        buf += chunk
    return buf


def reply(tid, uid, body):
    """组装 MBAP + PDU 响应帧"""
    return struct.pack(">HHHB", tid, 0, len(body) + 1, uid) + body


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        print("客户端连接:", self.client_address)
        conn = self.request
        try:
            while True:
                tid, _pid, length, uid = struct.unpack(">HHHB", recv_exact(conn, 7))
                pdu = recv_exact(conn, length - 1)
                if uid not in (UNIT_ID, 0xFF, 0):
                    continue                                  # 不是发给本从站的报文
                fc = pdu[0]
                if fc == 0x03:                                # 读保持寄存器
                    start, cnt = struct.unpack(">HH", pdu[1:5])
                    with LOCK:
                        vals = REGS[start:start + cnt]
                    if len(vals) != cnt:
                        conn.sendall(reply(tid, uid, struct.pack(">BB", 0x83, 0x02)))
                    else:
                        body = struct.pack(">BB", fc, cnt * 2)
                        body += b"".join(struct.pack(">H", v & 0xFFFF) for v in vals)
                        conn.sendall(reply(tid, uid, body))
                elif fc == 0x06:                              # 写单个寄存器
                    addr, val = struct.unpack(">HH", pdu[1:5])
                    if 0 <= addr < len(REGS):
                        with LOCK:
                            old = REGS[addr]
                            REGS[addr] = val
                            # 如果是继电器寄存器, 重算总电流
                            if addr in RELAY_REGS:
                                REGS[CURRENT_REG] = recalc_current()
                        conn.sendall(reply(tid, uid, pdu))    # 正常响应 = 回显请求
                        if addr in RELAY_REGS:
                            relay_idx = RELAY_REGS.index(addr) + 1
                            state = "开 ⚡" if val else "关 ⚪"
                            print(f"🔔 继电器{relay_idx} {state}  (0x{addr:04X}={val})  电流调整为 {REGS[CURRENT_REG]/10:.1f}A")
                        else:
                            print(f"写入寄存器 0x{addr:04X} : {old} → {val}")
                    else:
                        conn.sendall(reply(tid, uid, struct.pack(">BB", 0x86, 0x02)))
                else:                                         # 不支持的功能码
                    conn.sendall(reply(tid, uid, struct.pack(">BB", fc | 0x80, 0x01)))
        except (ConnectionError, OSError):
            pass
        finally:
            print("客户端断开:", self.client_address)


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def drift():
    """环境模拟: 温湿度缓慢漂移, 电压微小波动"""
    while True:
        time.sleep(2)
        with LOCK:
            REGS[0] = max(-100, min(600, REGS[0] + random.choice((-2, -1, 0, 1, 2))))
            REGS[1] = max(0, min(1000, REGS[1] + random.choice((-3, -1, 1, 2, 3))))
            # 电压在 218V~222V 间微小波动 (x10 存储: 2180~2220)
            REGS[VOLTAGE_REG] = max(2180, min(2220, REGS[VOLTAGE_REG] + random.choice((-2, -1, 0, 0, 1, 2))))


def main():
    threading.Thread(target=drift, daemon=True).start()
    with Server(("0.0.0.0", PORT), Handler) as srv:
        print(f"Modbus TCP 从站模拟器已启动: 0.0.0.0:{PORT} (unit_id={UNIT_ID})")
        print(f"寄存器布局:")
        print(f"  reg0  温度  (x10, 起始 {REGS[0]/10:.1f}°C)")
        print(f"  reg1  湿度  (x10, 起始 {REGS[1]/10:.1f}%RH)")
        print(f"  reg2-9 继电器1-8 (0=关/1=开)  共 {RELAY_COUNT} 路")
        print(f"  reg10 总电流 (x10, {REGS[CURRENT_REG]/10:.1f}A, 每开一路 +0.5A)")
        print(f"  reg11 电压  (x10, {REGS[VOLTAGE_REG]/10:.1f}V, 218~222V波动)")
        print(f"  reg12-15 预留")
        print("Ctrl+C 退出\n")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
