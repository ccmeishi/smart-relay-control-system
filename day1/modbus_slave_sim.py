"""Modbus TCP 从站模拟器(联调测试用)

作用: 在没有实验室从站(192.168.20.59:5502)的环境里, 本机模拟一台温湿度从站,
用于端到端联调 sensor_simulator.py。

模拟内容:
  保持寄存器 0x0000~0x0009 (unit_id=1)
    reg0 = 温度 x10(有符号)   起始 253 => 25.3 C
    reg1 = 湿度 x10(无符号)   起始 567 => 56.7 %RH
    reg2~reg9 = 0, 可用 FC6 写入
  每 2 秒温湿度随机漂移, 用于触发"值变化 -> MQTT 上报"

支持功能码: 0x03 读保持寄存器 / 0x06 写单个寄存器

用法:
  python modbus_slave_sim.py          # 监听 0.0.0.0:5502
  python modbus_slave_sim.py 5503     # 指定端口
"""

import random
import socketserver
import struct
import sys
import threading
import time

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 5502
UNIT_ID = 1
REGS = [253, 567] + [0] * 8
LOCK = threading.Lock()


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
                            REGS[addr] = val
                        conn.sendall(reply(tid, uid, pdu))    # 正常响应 = 回显请求
                        print("写入寄存器 0x%04X = %d" % (addr, val))
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
    """环境模拟: 温湿度缓慢漂移, 制造数据变化"""
    while True:
        time.sleep(2)
        with LOCK:
            REGS[0] = max(-100, min(600, REGS[0] + random.choice((-2, -1, 0, 1, 2))))
            REGS[1] = max(0, min(1000, REGS[1] + random.choice((-3, -1, 1, 2, 3))))


def main():
    threading.Thread(target=drift, daemon=True).start()
    with Server(("0.0.0.0", PORT), Handler) as srv:
        print("Modbus TCP 从站模拟器已启动: 0.0.0.0:%d (unit_id=%d, 寄存器 0x0000~0x0009)"
              % (PORT, UNIT_ID))
        print("Ctrl+C 退出")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
