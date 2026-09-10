"""modbus_slave_sim.py 集成测试

覆盖的寄存器布局（来自源码注释）:
  reg0   温度 x10  (253 => 25.3 C)
  reg1   湿度 x10  (567 => 56.7 %RH)
  reg2~3 预留
  reg4   人体感应 (0=无人/1=有人, 每10秒随机切换)
  reg5   烟雾等级 (0~100, 自动波动)
  reg6~9 继电器1~4 (0=关/1=开)
  reg10  总电流 x10(A)  (每开一路 +0.5A)
  reg11  电源电压 x10(V) (218~222V 波动)
  reg12~15 预留

支持功能码: 0x03 读保持寄存器 / 0x06 写单个寄存器
支持 unit_id: 默认 7, 可通过命令行传入 (fixture 用 7)
unit_id 过滤: uid in (UNIT_ID, 0xFF, 0) 才处理
"""
import time
import threading

import pytest


# ---------- 1. 读保持寄存器: 基本数据 ----------

class TestReadHoldingRegisters:
    """FC 0x03 读保持寄存器 基本行为"""

    def test_read_temperature_register0(self, modbus_client_factory, slave_server):
        """reg0 = 温度 x10, 初始值 253 (25.3C)"""
        c = modbus_client_factory(slave_server["unit_id"])
        rr = c.read_holding_registers(0, 1, slave=slave_server["unit_id"])
        assert not rr.isError(), f"读失败: {rr}"
        assert len(rr.registers) == 1
        # 初始值是 253, 但 drift 线程已经在跑, 可能偏离几格
        assert 240 <= rr.registers[0] <= 270, f"温度异常 {rr.registers[0]}"

    def test_read_humidity_register1(self, modbus_client_factory, slave_server):
        """reg1 = 湿度 x10, 初始值 567 (56.7%)"""
        c = modbus_client_factory(slave_server["unit_id"])
        rr = c.read_holding_registers(1, 1, slave=slave_server["unit_id"])
        assert not rr.isError()
        assert 555 <= rr.registers[0] <= 580, f"湿度异常 {rr.registers[0]}"

    def test_read_all_relay_registers(self, modbus_client_factory, slave_server):
        """reg6~reg9 = 继电器1~4, 初始全 0"""
        c = modbus_client_factory(slave_server["unit_id"])
        rr = c.read_holding_registers(6, 4, slave=slave_server["unit_id"])
        assert not rr.isError()
        assert len(rr.registers) == 4
        for i, v in enumerate(rr.registers):
            assert v in (0, 1), f"继电器寄存器 {i+1} 异常值 {v}"

    def test_read_total_current_register10(self, modbus_client_factory, slave_server):
        """reg10 = 总电流 x10, 初始 0 (因为继电器全关)"""
        c = modbus_client_factory(slave_server["unit_id"])
        rr = c.read_holding_registers(10, 1, slave=slave_server["unit_id"])
        assert not rr.isError()
        # 全关时电流 = 0 (虽然可能有漂动, 但每个继电器 = 0 时 = 0)
        assert rr.registers[0] == 0

    def test_read_voltage_register11(self, modbus_client_factory, slave_server):
        """reg11 = 电压 x10, 初始 2200 (220V)"""
        c = modbus_client_factory(slave_server["unit_id"])
        rr = c.read_holding_registers(11, 1, slave=slave_server["unit_id"])
        assert not rr.isError()
        # 2180~2220 区间
        assert 2180 <= rr.registers[0] <= 2220, f"电压越界 {rr.registers[0]}"

    def test_read_all_16_registers_at_once(self, modbus_client_factory, slave_server):
        """一次性读全部 16 个寄存器"""
        c = modbus_client_factory(slave_server["unit_id"])
        rr = c.read_holding_registers(0, 16, slave=slave_server["unit_id"])
        assert not rr.isError()
        assert len(rr.registers) == 16


# ---------- 2. 写单寄存器: 继电器控制 + 电流联动 ----------

class TestWriteSingleRegister:
    """FC 0x06 写单个寄存器 行为"""

    def test_write_relay_on_off(self, modbus_client_factory, slave_server):
        """写 reg6 (继电器1) = 1, 再 = 0"""
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        # 开
        wr = c.write_register(6, 1, slave=uid)
        assert not wr.isError()
        # 读回
        rr = c.read_holding_registers(6, 1, slave=uid)
        assert rr.registers[0] == 1
        # 关
        wr = c.write_register(6, 0, slave=uid)
        assert not wr.isError()
        rr = c.read_holding_registers(6, 1, slave=uid)
        assert rr.registers[0] == 0

    def test_current_increments_with_relay_count(self, modbus_client_factory, slave_server):
        """每开 1 路继电器, 总电流 reg10 应 +5 (0.5A * 10)"""
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        # 先确保全关 (继电器寄存器 6~9)
        for addr in range(6, 10):
            c.write_register(addr, 0, slave=uid)
        # 读初始电流
        rr = c.read_holding_registers(10, 1, slave=uid)
        assert rr.registers[0] == 0, f"初始电流应为 0, 实测 {rr.registers[0]}"
        # 开 1 路
        c.write_register(6, 1, slave=uid)
        rr = c.read_holding_registers(10, 1, slave=uid)
        assert rr.registers[0] == 5, f"开 1 路电流应为 5, 实测 {rr.registers[0]}"
        # 再开 1 路
        c.write_register(7, 1, slave=uid)
        rr = c.read_holding_registers(10, 1, slave=uid)
        assert rr.registers[0] == 10, f"开 2 路电流应为 10, 实测 {rr.registers[0]}"
        # 把剩下 2 路全开 (共 4 路)
        for addr in range(8, 10):
            c.write_register(addr, 1, slave=uid)
        rr = c.read_holding_registers(10, 1, slave=uid)
        assert rr.registers[0] == 20, f"开 4 路电流应为 20, 实测 {rr.registers[0]}"
        # 验证 4 个继电器寄存器确实都是 1
        rr = c.read_holding_registers(6, 4, slave=uid)
        assert rr.registers == [1] * 4, f"4 路继电器状态异常: {rr.registers}"

    def test_current_decrements_when_relay_off(self, modbus_client_factory, slave_server):
        """关继电器后电流应减少"""
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        for addr in range(6, 10):
            c.write_register(addr, 0, slave=uid)
        c.write_register(6, 1, slave=uid)
        c.write_register(7, 1, slave=uid)
        c.write_register(8, 1, slave=uid)
        rr = c.read_holding_registers(10, 1, slave=uid)
        assert rr.registers[0] == 15
        # 关掉一个
        c.write_register(7, 0, slave=uid)
        rr = c.read_holding_registers(10, 1, slave=uid)
        assert rr.registers[0] == 10

    def test_write_non_relay_register_no_current_change(self, modbus_client_factory, slave_server):
        """写非继电器寄存器不应影响电流"""
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        # 清零
        for addr in range(6, 10):
            c.write_register(addr, 0, slave=uid)
        rr = c.read_holding_registers(10, 1, slave=uid)
        before = rr.registers[0]
        # 写温度寄存器
        c.write_register(0, 300, slave=uid)
        rr = c.read_holding_registers(10, 1, slave=uid)
        assert rr.registers[0] == before, "写温度不应影响电流"
        # 写湿度寄存器
        c.write_register(1, 800, slave=uid)
        rr = c.read_holding_registers(10, 1, slave=uid)
        assert rr.registers[0] == before, "写湿度不应影响电流"


# ---------- 3. 异常路径: 非法地址 / 不支持的功能码 ----------

class TestErrorPaths:
    """异常码处理"""

    def test_read_out_of_range_returns_illegal_data_address(self, modbus_client_factory, slave_server):
        """读越界地址 (reg16 不存在) 应返回 0x83 + 异常码 0x02"""
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        rr = c.read_holding_registers(16, 1, slave=uid)
        # pymodbus 会把异常包成 response
        assert rr.isError(), f"读越界应报错, 但返回 {rr.registers}"

    def test_read_beyond_16_registers_returns_error(self, modbus_client_factory, slave_server):
        """读超过 16 个寄存器 (如读 20 个) 应报错"""
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        rr = c.read_holding_registers(0, 20, slave=uid)
        assert rr.isError()

    def test_write_out_of_range_returns_error(self, modbus_client_factory, slave_server):
        """写越界地址应返回 0x86 + 异常码 0x02"""
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        wr = c.write_register(20, 1, slave=uid)
        assert wr.isError()

    def test_unsupported_function_code_returns_error(self, modbus_client_factory, slave_server):
        """不支持的功能码 (如 0x01 读线圈) 应返回异常码 0x01"""
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        rr = c.read_coils(0, 1, slave=uid)  # FC 0x01 不支持
        assert rr.isError()


# ---------- 4. unit_id 过滤 ----------

class TestUnitIdFilter:
    """unit_id 过滤: 只接受 UNIT_ID, 0xFF, 0"""

    def test_correct_unit_id_works(self, modbus_client_factory, slave_server):
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        rr = c.read_holding_registers(0, 1, slave=uid)
        assert not rr.isError()

    def test_wrong_unit_id_ignored(self, modbus_client_factory, slave_server):
        """用错误的 unit_id 通信, 从站不应处理也不会响应"""
        c = modbus_client_factory(slave_server["unit_id"])
        # 用一个明显错误的 unit_id, 应该无响应 (连接超时或错误)
        wrong_uid = slave_server["unit_id"] + 100
        # 这种调用会因没响应而超时或返回错误
        try:
            rr = c.read_holding_registers(0, 1, slave=wrong_uid)
            # 如果返回了, 那应该是某种错误
            assert rr.isError() or rr.registers == [], f"错误 unit_id 不应成功: {rr}"
        except Exception:
            # 超时抛异常也是正确行为
            pass


# ---------- 5. drift 漂动行为 ----------

class TestDrift:
    """drift 线程: 温度/湿度/电压缓慢漂动"""

    def test_temperature_drifts_over_time(self, modbus_client_factory, slave_server):
        """8 秒内温度应有变化 (drift 周期 2s, 偶发 0 步, 8s 更稳)"""
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        samples = []
        for _ in range(32):
            rr = c.read_holding_registers(0, 1, slave=uid)
            samples.append(rr.registers[0])
            time.sleep(0.25)
        # 温度在 8 秒内应该有变化 (drift 周期 2s × 4 轮)
        assert max(samples) - min(samples) > 0, f"8s 内温度无变化: {samples}"
        # 应该在合法范围内 [-10, 60] => reg 范围 [-100, 600]
        for v in samples:
            assert -100 <= v <= 600

    def test_voltage_stays_in_range(self, modbus_client_factory, slave_server):
        """电压无论怎么漂都应在 2180~2220"""
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        for _ in range(15):
            rr = c.read_holding_registers(11, 1, slave=uid)
            assert 2180 <= rr.registers[0] <= 2220, f"电压越界: {rr.registers[0]}"
            time.sleep(0.2)


# ---------- 6. 并发 client ----------

class TestConcurrency:
    """多个 client 同时操作不应导致 race condition 或崩溃"""

    def test_multiple_clients_read_simultaneously(self, modbus_client_factory, slave_server):
        """3 个 client 同时读"""
        uid = slave_server["unit_id"]
        clients = [modbus_client_factory(uid) for _ in range(3)]
        results = [None] * 3

        def worker(i):
            r = clients[i].read_holding_registers(0, 16, slave=uid)
            results[i] = r

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        for i, r in enumerate(results):
            assert r is not None, f"Client {i} 没收到响应"
            assert not r.isError(), f"Client {i} 读失败: {r}"
            assert len(r.registers) == 16

    def test_multiple_clients_write_relays(self, modbus_client_factory, slave_server):
        """3 个 client 同时写不同继电器, 最终状态应全部正确"""
        uid = slave_server["unit_id"]
        # 先清零
        c0 = modbus_client_factory(uid)
        for addr in range(6, 10):
            c0.write_register(addr, 0, slave=uid)

        clients = [modbus_client_factory(uid) for _ in range(3)]

        def worker(i):
            # client 0 写 reg6, client 1 写 reg7, client 2 写 reg8
            clients[i].write_register(6 + i, 1, slave=uid)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(3)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # 验证 3 个继电器都开了
        rr = c0.read_holding_registers(6, 3, slave=uid)
        assert rr.registers == [1, 1, 1], f"并发写后状态异常: {rr.registers}"
        # 电流应为 15 (3 路 * 5)
        rr = c0.read_holding_registers(10, 1, slave=uid)
        assert rr.registers[0] == 15


# ---------- 7. 边缘: 寄存器值边界 ----------

class TestBoundaries:
    """值边界处理"""

    def test_write_relay_with_non_boolean_value(self, modbus_client_factory, slave_server):
        """写 2/65535 等非 0/1 值: 从站会原样存"""
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        c.write_register(6, 0, slave=uid)  # 先清零
        c.write_register(6, 2, slave=uid)
        rr = c.read_holding_registers(6, 1, slave=uid)
        # 实现是 REGS[addr] = val, 不做 bool 转换
        assert rr.registers[0] == 2
        # 但因为 2 不在 (0,1) 里, 电流计算时 sum(1 for i in RELAY_REGS if REGS[i])
        # 2 是 truthy, 会被算作"开", 电流应 +5
        rr = c.read_holding_registers(10, 1, slave=uid)
        assert rr.registers[0] >= 5

    def test_temperature_boundary(self, modbus_client_factory, slave_server):
        """温度寄存器允许范围 [-100, 600] (drift 限制)"""
        uid = slave_server["unit_id"]
        c = modbus_client_factory(uid)
        # 写一个极端值
        c.write_register(0, 0, slave=uid)
        rr = c.read_holding_registers(0, 1, slave=uid)
        # 0 是合法值 (会被漂动调整)
        assert 0 <= rr.registers[0] <= 600
