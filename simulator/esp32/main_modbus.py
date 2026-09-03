"""路线B: ESP32 作为 Modbus TCP 从站 (MicroPython)

寄存器布局模仿实验室从站 (unit_id=7), PC 端 relay_simulator_jl.py
只改两个配置就能把"从站"从 192.168.20.59:5502 换成这块板子:
  config_relay.json -> "host": "<ESP32的IP>", "port": 502
  (启动后串口会打印本机 IP)

寄存器布局:
  reg0 = 温度 x10 (静态 253 => 25.3C, 实物无传感器)
  reg1 = 湿度 x10 (静态 567)
  reg2~reg5 = 继电器1~4 (0=关/1=开, 双向联动 GPIO)
  reg6~reg9 = 恒 0 (占位, 对齐 PC 模拟器读 reg2~9 的习惯)

支持功能码: 0x03 读保持寄存器 / 0x06 写单寄存器 / 0x10 写多寄存器

上传到板子:
  mpremote cp config.py relay_hw.py main_modbus.py :/
  mpremote cp main_modbus.py :/main.py
  mpremote reset
"""
import socket
import ustruct
import network
import config as C
import relay_hw

REGS = [253, 567, 1, 1, 1, 1, 0, 0, 0, 0, 0, 0]   # reg2~5 初始 1 对应上电全亮
RELAY_ADDR = (2, 3, 4, 5)               # reg2~reg5 = 继电器1~4


def log(*args):
    print("[modbus]", *args)


def sync_from_hw():
    """读寄存器前, 先把 GPIO 实际状态同步进 reg2~5"""
    for i, addr in enumerate(RELAY_ADDR):
        REGS[addr] = relay_hw.get(i)


def drive_hw(addr, val):
    """写 reg2~5 时联动 GPIO"""
    if addr in RELAY_ADDR:
        relay_hw.set(RELAY_ADDR.index(addr), 1 if val else 0)


def reply(tid, uid, body):
    return ustruct.pack(">HHHB", tid, 0, len(body) + 1, uid) + body


def recv_exact(conn, n):
    buf = b""
    while len(buf) < n:
        chunk = conn.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("对端断开")
        buf += chunk
    return buf


def handle(conn):
    tid, _pid, length, uid = ustruct.unpack(">HHHB", recv_exact(conn, 7))
    pdu = recv_exact(conn, length - 1)
    if uid not in (C.MODBUS_UNIT_ID, 0xFF, 0):
        return

    fc = pdu[0]
    if fc == 0x03:                                       # 读保持寄存器
        start, cnt = ustruct.unpack(">HH", pdu[1:5])
        sync_from_hw()
        if start + cnt > len(REGS):
            conn.sendall(reply(tid, uid, ustruct.pack(">BB", 0x83, 0x02)))
        else:
            body = ustruct.pack(">BB", fc, cnt * 2)
            for v in REGS[start:start + cnt]:
                body += ustruct.pack(">H", v)
            conn.sendall(reply(tid, uid, body))
            log("读 reg%d~%d = %s" % (start, start + cnt - 1,
                                      REGS[start:start + cnt]))

    elif fc == 0x06:                                     # 写单寄存器
        addr, val = ustruct.unpack(">HH", pdu[1:5])
        if addr < len(REGS):
            REGS[addr] = val
            drive_hw(addr, val)
            conn.sendall(reply(tid, uid, pdu))           # 正常响应=回显请求
            if addr in RELAY_ADDR:
                log("继电器%d -> %s" % (addr - 1, "开" if val else "关"))
        else:
            conn.sendall(reply(tid, uid, ustruct.pack(">BB", 0x86, 0x02)))

    elif fc == 0x10:                                     # 写多寄存器
        start, cnt = ustruct.unpack(">HH", pdu[1:5])
        bc = pdu[5]
        vals = ustruct.unpack(">%dH" % cnt, pdu[6:6 + bc])
        for i, v in enumerate(vals):
            addr = start + i
            if addr < len(REGS):
                REGS[addr] = v
                drive_hw(addr, v)
        conn.sendall(reply(tid, uid, ustruct.pack(">BHH", 0x10, start, cnt)))
        log("批量写 reg%d 起 %d 个" % (start, cnt))

    else:                                                # 不支持的功能码
        conn.sendall(reply(tid, uid, ustruct.pack(">BB", 0x80 | fc, 0x01)))


def run():
    wlan = network.WLAN(network.STA_IF)
    if not wlan.isconnected():
        raise OSError("WiFi 未连接, 请先检查 boot.py / config.py")
    ip = wlan.ifconfig()[0]

    relay_hw.init()
    relay_hw.attach_button()     # 板载BOOT键: 按一次 4路全开<->全关 (PC轮询自动读到)
    s = socket.socket()
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", C.MODBUS_PORT))
    s.listen(1)
    log("Modbus TCP 从站已启动 %s:%s  unit_id=%d" %
        (ip, C.MODBUS_PORT, C.MODBUS_UNIT_ID))
    log("PC 端 config_relay.json 改为: host=%s, port=%d" % (ip, C.MODBUS_PORT))

    while True:
        conn, addr = s.accept()
        log("客户端接入:", addr)
        conn.settimeout(120)
        try:
            while True:
                handle(conn)
        except Exception as e:
            log("连接结束:", e)
        try:
            conn.close()
        except Exception:
            pass


run()
