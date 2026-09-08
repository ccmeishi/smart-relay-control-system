"""Modbus 采集网关 (Day8): Modbus TCP 主站, 时间片轮询, 只读

在 mqtt_loop() 中每轮调用 poll_one(), 每次只读一个寄存器点,
socket 超时 1 秒, 不阻塞继电器控制和 MQTT 消息处理。

Day8 变化: 移除 Day7 的 write/supports_write 反向链路。
拆分架构后 sensor 设备是纯只读采集代理, 不再支持云端写温度。
JetLinks 下发属性只对 relay 设备生效 (GPIO 操作), sensor 设备只读忽略。

配置格式 (config.json):
{
  "modbus_slaves": [
    {
      "name": "sensor1",
      "host": "192.168.30.100",
      "port": 502,
      "unit_id": 1,
      "points": [
        {"addr": "0x0000", "key": "temperature", "period_ms": 3000,
         "count": 1, "type": "uint16", "scale": 0.1},
        {"addr": "0x0001", "key": "humidity",    "period_ms": 5000,
         "count": 1, "type": "uint16", "scale": 0.1}
      ]
    }
  ]
}

数据类型: int16 / uint16 (1寄存器), uint32 / int32 (2寄存器), float_be (2寄存器大端浮点)
"""
import time
import struct
import socket


# ---------- Modbus TCP 帧编解码 ----------

_TRANSACTION = 0


def _next_tid():
    global _TRANSACTION
    _TRANSACTION = (_TRANSACTION + 1) & 0xFFFF
    return _TRANSACTION


def _mbap(unit_id, pdu):
    """构造 Modbus TCP 帧 (MBAP头 + PDU)"""
    tid = _next_tid()
    length = 1 + len(pdu)  # unit_id + PDU
    mbap = struct.pack(">HHHB", tid, 0, length, unit_id)
    return mbap + pdu, tid


def _parse_response(frame, expected_tid):
    """解析 Modbus TCP 响应, 返回 (unit_id, func_code, pdu_data) 或 None"""
    if len(frame) < 8:
        return None
    tid, proto, length, unit_id = struct.unpack(">HHHB", frame[:7])
    if tid != expected_tid or proto != 0:
        return None
    if length < 2 or len(frame) < 6 + length:
        return None
    pdu = frame[7:7 + length]
    func = pdu[0]
    if func & 0x80:
        return None  # 异常响应
    return unit_id, func, pdu[1:]


def _decode_registers(raw, count, dtype):
    """按 dtype 解码寄存器数据"""
    if len(raw) < count * 2:
        return None
    if dtype == "uint16":
        return struct.unpack(">H", raw[:2])[0]
    elif dtype == "int16":
        return struct.unpack(">h", raw[:2])[0]
    elif dtype == "uint32":
        return struct.unpack(">I", raw[:4])[0]
    elif dtype == "int32":
        return struct.unpack(">i", raw[:4])[0]
    elif dtype == "float_be":
        return struct.unpack(">f", raw[:4])[0]
    else:
        return struct.unpack(">H", raw[:2])[0]


# ---------- Socket 连接管理 ----------

class _SlaveConn:
    """单个从站的 TCP 连接 (长连接复用, 断线重连, 失败冷却)"""

    def __init__(self, host, port, timeout_s=1.0):
        self.host = host
        self.port = port
        self.timeout = timeout_s
        self.sock = None
        self.fail_count = 0
        self.retry_after = 0

    def _in_cooldown(self):
        if self.retry_after and time.ticks_ms() < self.retry_after:
            return True
        return False

    def connect(self):
        self.close()
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(self.timeout)
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            except Exception:
                pass
            s.connect((self.host, self.port))
            self.sock = s
            self.fail_count = 0
            self.retry_after = 0
            return True
        except OSError as e:
            print("[modbus] connect fail %s:%d -> %s" % (self.host, self.port, e))
            self.sock = None
            self.fail_count += 1
            if self.fail_count >= 3:
                self.retry_after = time.ticks_add(time.ticks_ms(), 3000)
                print("[modbus] %s:%d cooling down 3s" % (self.host, self.port))
            return False

    def close(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def read_holding(self, unit_id, start_addr, count):
        """读保持寄存器 0x03, 返回 bytes 或 None"""
        if self._in_cooldown():
            return None
        if self.sock is None:
            if not self.connect():
                return None
        pdu = struct.pack(">BHH", 0x03, start_addr, count)
        frame, tid = _mbap(unit_id, pdu)
        try:
            self.sock.sendall(frame)
            head = self._recv_exact(7)
            if head is None:
                self._on_fail()
                return None
            _, _, length, _unit = struct.unpack(">HHHB", head)
            pdu_len = length - 1
            pdu = self._recv_exact(pdu_len)
            if pdu is None:
                self._on_fail()
                return None
            full = head + pdu
            parsed = _parse_response(full, tid)
            if parsed is None:
                self._on_fail()
                return None
            _uid, func, data = parsed
            if func == 0x03 and len(data) >= 1:
                byte_count = data[0]
                regs = data[1:1 + byte_count]
                return regs
            return None
        except OSError as e:
            print("[modbus] 通信异常 %s:%d -> %s" % (self.host, self.port, e))
            self._on_fail()
            return None

    def write_holding(self, unit_id, addr, value):
        """写单个保持寄存器 0x06, 成功返回 True, 失败返回 False"""
        if self._in_cooldown():
            return False
        if self.sock is None:
            if not self.connect():
                return False
        pdu = struct.pack(">BHH", 0x06, addr, value & 0xFFFF)
        frame, tid = _mbap(unit_id, pdu)
        try:
            self.sock.sendall(frame)
            head = self._recv_exact(7)
            if head is None:
                self._on_fail()
                return False
            parsed = _parse_response(head, tid)
            if parsed is None:
                self._on_fail()
                return False
            _uid, func, data = parsed
            if func == 0x06:
                return True
            return False
        except OSError as e:
            print("[modbus] 写寄存器异常:", e)
            self._on_fail()
            return False

    def _recv_exact(self, n):
        buf = b""
        while len(buf) < n:
            try:
                chunk = self.sock.recv(n - len(buf))
            except OSError:
                return None
            if not chunk:
                return None
            buf += chunk
        return buf

    def _on_fail(self):
        """通信失败 -> 关闭 socket, 计数, 达阈值进冷却"""
        self.fail_count += 1
        self.close()
        if self.fail_count >= 3:
            self.retry_after = time.ticks_add(time.ticks_ms(), 3000)
            print("[modbus] %s:%d cooling down 3s" % (self.host, self.port))


# ---------- 采集网关 ----------

class ModbusGateway:
    """时间片轮转的 Modbus 采集调度器 (只读)"""

    def __init__(self, slaves_cfg):
        self.enabled = bool(slaves_cfg)
        self.conns = {}
        self.points = []
        self.values = {}
        self._parse_slaves(slaves_cfg)

    def _parse_slaves(self, slaves_cfg):
        if not slaves_cfg:
            self.enabled = False
            return
        for si, slave in enumerate(slaves_cfg):
            host = slave.get("host", "")
            port = int(slave.get("port", 502))
            unit_id = int(slave.get("unit_id", 1))
            if not host:
                continue
            key = (host, port, unit_id)
            if key not in self.conns:
                self.conns[key] = _SlaveConn(host, port)
            conn = self.conns[key]
            for pi, pt in enumerate(slave.get("points", [])):
                addr_str = pt.get("addr", "0x0000")
                try:
                    addr = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)
                except ValueError:
                    continue
                period = int(pt.get("period_ms", 5000))
                count = int(pt.get("count", 1))
                dtype = pt.get("type", "uint16")
                pkey = pt.get("key", "")
                scale = pt.get("scale", None)
                if not pkey:
                    continue
                self.points.append({
                    "conn": conn, "unit_id": unit_id,
                    "addr": addr, "count": count, "type": dtype,
                    "key": pkey, "period": period, "scale": scale,
                    "next_due": time.ticks_add(time.ticks_ms(), 1000 + pi * 500),
                })
        if not self.points:
            self.enabled = False

    def poll_one(self):
        """时间片: 只读取下一个到期的采集点, 非阻塞"""
        if not self.enabled or not self.points:
            return
        now = time.ticks_ms()
        best = None
        for pt in self.points:
            if time.ticks_diff(now, pt["next_due"]) >= 0:
                if best is None or time.ticks_diff(pt["next_due"], best["next_due"]) < 0:
                    best = pt
        if best is None:
            return
        conn = best["conn"]
        regs = conn.read_holding(best["unit_id"], best["addr"], best["count"])
        if regs is not None:
            val = _decode_registers(regs, best["count"], best["type"])
            if val is not None:
                if best.get("scale") is not None:
                    val = round(val * best["scale"], 2)
                self.values[best["key"]] = val
                conn.fail_count = 0
                print("[modbus] %s = %s (addr=%s, type=%s)" % (
                    best["key"], val, hex(best["addr"]), best["type"]))
        best["next_due"] = time.ticks_add(now, best["period"])

    def collected(self):
        """返回最新采集值的拷贝"""
        return dict(self.values)

    def point_count(self):
        return len(self.points)

    def close_all(self):
        for c in self.conns.values():
            c.close()


# ---------- 模块级便捷函数 ----------

_gw_instance = None


def init(slaves_cfg):
    """初始化全局网关实例."""
    global _gw_instance
    if _gw_instance is not None:
        _gw_instance.close_all()
    _gw_instance = ModbusGateway(slaves_cfg)
    return _gw_instance


def poll_one():
    if _gw_instance:
        _gw_instance.poll_one()


def collected():
    if _gw_instance:
        return _gw_instance.collected()
    return {}


def point_count():
    if _gw_instance:
        return _gw_instance.point_count()
    return 0


def close():
    if _gw_instance:
        _gw_instance.close_all()
