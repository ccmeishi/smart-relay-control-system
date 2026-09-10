"""sensor_simulator.py 单元测试

覆盖目标文件：simulator/day1/sensor_simulator.py

测试策略：
- 直接 import 整个模块（虽然它有顶层副作用，但都是声明/常量，不影响测试）
- 把全局 mqtt_client 替换为 MagicMock，避免任何真实 MQTT 连接
- 用 tmp_path 提供临时 JSON 文件

覆盖范围：
- to_signed()：16 位有符号转换
- parse_values()：寄存器数组按 register_map 解析成物理量
- brief_line()：payload 摘要生成
- load_json() / save_json()：JSON 读写
- on_cmd()：MQTT 命令回调分发
- 协议层不变量：register_map 字段定义、上报 payload 格式
"""
import importlib
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


SENSOR_SIM_PATH = (
    Path(__file__).resolve().parent.parent / "day1" / "sensor_simulator.py"
)
DAY1_DIR = str(SENSOR_SIM_PATH.parent)


@pytest.fixture
def sensor_sim():
    """导入 sensor_simulator 模块，隔离全局状态"""
    if DAY1_DIR not in sys.path:
        sys.path.insert(0, DAY1_DIR)
    if "sensor_simulator" in sys.modules:
        importlib.reload(sys.modules["sensor_simulator"])
    import sensor_simulator as ss

    # 替换全局 mqtt_client 为 mock
    ss.mqtt_client = MagicMock()
    return ss


# ---------- 1. 纯函数：to_signed ----------

class TestToSigned:
    """16 位有符号寄存器转换"""

    def test_positive_small(self, sensor_sim):
        """< 32768 应保持原值"""
        assert sensor_sim.to_signed(0) == 0
        assert sensor_sim.to_signed(100) == 100
        assert sensor_sim.to_signed(32767) == 32767

    def test_negative_via_complement(self, sensor_sim):
        """> 32767 应减去 65536 变成负数"""
        assert sensor_sim.to_signed(32768) == -32768
        assert sensor_sim.to_signed(65535) == -1
        assert sensor_sim.to_signed(50000) == -15536

    def test_boundary_values(self, sensor_sim):
        """边界值"""
        assert sensor_sim.to_signed(32767) == 32767
        assert sensor_sim.to_signed(32768) == -32768


# ---------- 2. 纯函数：parse_values ----------

class TestParseValues:
    """寄存器按 register_map 解析成物理量"""

    def test_basic_temperature_humidity(self, sensor_sim):
        """温度（x10 有符号）+ 湿度（x10 无符号）"""
        reg_map = {
            "0": {"name": "temperature", "scale": 0.1, "signed": True, "unit": "C"},
            "1": {"name": "humidity", "scale": 0.1, "signed": False, "unit": "%RH"},
        }
        regs = [253, 567]  # 25.3°C, 56.7%RH
        result = sensor_sim.parse_values(regs, reg_map)
        assert result == {"temperature": 25.3, "humidity": 56.7}

    def test_negative_temperature(self, sensor_sim):
        """温度可能为负，signed=True 转换"""
        reg_map = {
            "0": {"name": "temperature", "scale": 0.1, "signed": True, "unit": "C"},
        }
        regs = [65302]  # 有符号 -234 / 0.1 = -23.4°C
        result = sensor_sim.parse_values(regs, reg_map)
        assert result == {"temperature": -23.4}

    def test_missing_register_skipped(self, sensor_sim):
        """regs 比 register_map 短时，跳过越界项"""
        reg_map = {
            "0": {"name": "temperature", "scale": 0.1, "signed": True, "unit": "C"},
            "1": {"name": "humidity", "scale": 0.1, "signed": False, "unit": "%RH"},
            "5": {"name": "extra", "scale": 1, "signed": False, "unit": ""},
        }
        regs = [253, 567]  # 缺少索引 5
        result = sensor_sim.parse_values(regs, reg_map)
        assert "extra" not in result
        assert result == {"temperature": 25.3, "humidity": 56.7}

    def test_default_scale_one(self, sensor_sim):
        """scale 字段缺失时默认 1（不缩放）"""
        reg_map = {
            "0": {"name": "raw", "signed": False, "unit": ""},  # 无 scale
        }
        regs = [1234]
        result = sensor_sim.parse_values(regs, reg_map)
        assert result == {"raw": 1234}

    def test_unsigned_treats_32768_as_32768(self, sensor_sim):
        """unsigned 不做 to_signed 转换"""
        reg_map = {
            "0": {"name": "v", "scale": 1, "signed": False, "unit": ""},
        }
        regs = [65535]  # 如果 signed 会变 -1，这里应保持 65535
        result = sensor_sim.parse_values(regs, reg_map)
        assert result == {"v": 65535}

    def test_empty_registers(self, sensor_sim):
        """空寄存器列表返回空字典"""
        reg_map = {"0": {"name": "x", "scale": 1, "signed": False, "unit": ""}}
        assert sensor_sim.parse_values([], reg_map) == {}

    def test_empty_register_map(self, sensor_sim):
        """空映射也返回空字典"""
        assert sensor_sim.parse_values([1, 2, 3], {}) == {}


# ---------- 3. 纯函数：brief_line ----------

class TestBriefLine:
    """brief_line 把 payload 压成一行终端摘要"""

    def test_data_with_temperature_humidity(self, sensor_sim):
        s = sensor_sim.brief_line({"type": "data", "temperature": 25.3, "humidity": 56.7})
        assert "温度" in s and "25.3" in s
        assert "湿度" in s and "56.7" in s

    def test_data_with_only_registers(self, sensor_sim):
        """没解析出 temperature 时显示原始寄存器（无空格格式：[1,2,3]）"""
        s = sensor_sim.brief_line({"type": "data", "registers": [1, 2, 3]})
        assert "寄存器" in s
        # 源码主动去掉了空格，断言实际格式
        assert "[1,2,3]" in s

    def test_heartbeat(self, sensor_sim):
        s = sensor_sim.brief_line({"type": "heartbeat", "uptime": 120})
        assert "心跳" in s
        assert "120s" in s

    def test_online(self, sensor_sim):
        s = sensor_sim.brief_line({"type": "online"})
        assert "上线" in s

    def test_write_ack_uses_reg_base(self, sensor_sim):
        """write_ack 的 register 偏移会加上 reg_base（终端显示用）"""
        # 设置 reg_base 全局变量
        sensor_sim.reg_base = 0x0000
        s = sensor_sim.brief_line({"type": "write_ack", "register": 2, "value": 1})
        assert "寄存器0x0002" in s
        assert "1" in s

        sensor_sim.reg_base = 0x0010
        s = sensor_sim.brief_line({"type": "write_ack", "register": 0, "value": 0})
        assert "寄存器0x0010" in s

    def test_error(self, sensor_sim):
        s = sensor_sim.brief_line({"type": "error", "detail": "Modbus 断开"})
        assert "错误" in s
        assert "Modbus 断开" in s

    def test_unknown_type(self, sensor_sim):
        """未知 type 返回字符串形式"""
        s = sensor_sim.brief_line({"type": "weird_thing"})
        # 不抛异常即可
        assert isinstance(s, str)


# ---------- 4. JSON 文件操作 ----------

class TestJsonIO:
    """load_json / save_json"""

    def test_load_existing(self, sensor_sim, tmp_path):
        p = tmp_path / "cfg.json"
        p.write_text('{"host": "1.2.3.4", "port": 5502}', encoding="utf-8")
        result = sensor_sim.load_json(str(p), default={"host": "default"})
        assert result == {"host": "1.2.3.4", "port": 5502}

    def test_load_missing_returns_default(self, sensor_sim, tmp_path):
        p = tmp_path / "not_exists.json"
        result = sensor_sim.load_json(str(p), default={"fallback": True})
        assert result == {"fallback": True}

    def test_load_corrupt_returns_default(self, sensor_sim, tmp_path):
        p = tmp_path / "bad.json"
        p.write_text("not valid json {{{", encoding="utf-8")
        result = sensor_sim.load_json(str(p), default={"ok": True})
        assert result == {"ok": True}

    def test_save_and_load_roundtrip(self, sensor_sim, tmp_path):
        p = tmp_path / "store.json"
        data = {"registers": [1, 2, 3], "values": {"temperature": 25.5}}
        sensor_sim.save_json(str(p), data)
        loaded = sensor_sim.load_json(str(p), default={})
        assert loaded == data

    def test_save_chinese_unicode(self, sensor_sim, tmp_path):
        """中文应正确编码（ensure_ascii=False）"""
        p = tmp_path / "cn.json"
        sensor_sim.save_json(str(p), {"msg": "中文测试 温度"})
        raw = p.read_text(encoding="utf-8")
        # 应该是真正的中文，不是 \u 转义
        assert "中文测试" in raw
        # roundtrip
        loaded = sensor_sim.load_json(str(p), default={})
        assert loaded == {"msg": "中文测试 温度"}


# ---------- 5. MQTT 命令回调 on_cmd ----------

class TestOnCmd:
    """on_cmd 解析 MQTT 下发命令"""

    def _make_msg(self, payload_text):
        msg = MagicMock()
        msg.payload = payload_text.encode("utf-8")
        return msg

    def test_write_command_queued(self, sensor_sim):
        """write 命令应入队 wq"""
        # 清空可能残留的 wq 项
        while not sensor_sim.wq.empty():
            sensor_sim.wq.get()
        msg = self._make_msg(json.dumps({"cmd": "write", "register": 2, "value": 1}))
        sensor_sim.on_cmd(None, None, msg)
        # 应入队 1 条 ("write", 2, 1)
        assert not sensor_sim.wq.empty()
        job = sensor_sim.wq.get()
        assert job == ("write", 2, 1)
        # 不应 publish error
        sensor_sim.mqtt_client.publish.assert_not_called()

    def test_read_command_queued(self, sensor_sim):
        while not sensor_sim.wq.empty():
            sensor_sim.wq.get()
        msg = self._make_msg(json.dumps({"cmd": "read"}))
        sensor_sim.on_cmd(None, None, msg)
        job = sensor_sim.wq.get()
        assert job == ("read",)

    def test_query_command_queued(self, sensor_sim):
        while not sensor_sim.wq.empty():
            sensor_sim.wq.get()
        msg = self._make_msg(json.dumps({"cmd": "query"}))
        sensor_sim.on_cmd(None, None, msg)
        job = sensor_sim.wq.get()
        assert job == ("query",)

    def test_bad_json_publishes_error(self, sensor_sim):
        """非 JSON 报文应 publish error 不抛异常"""
        msg = self._make_msg("not json {{{")
        sensor_sim.on_cmd(None, None, msg)
        # 应调用 publish
        assert sensor_sim.mqtt_client.publish.called
        call = sensor_sim.mqtt_client.publish.call_args
        payload_text = call.args[1]
        payload = json.loads(payload_text)
        assert payload["type"] == "error"
        assert "bad json" in payload["detail"]

    def test_write_missing_register_publishes_error(self, sensor_sim):
        """write 缺 register 应 publish error"""
        msg = self._make_msg(json.dumps({"cmd": "write", "value": 1}))
        sensor_sim.on_cmd(None, None, msg)
        # 不应入队
        assert sensor_sim.wq.empty()
        # 应 publish error
        assert sensor_sim.mqtt_client.publish.called
        payload = json.loads(sensor_sim.mqtt_client.publish.call_args.args[1])
        assert payload["type"] == "error"

    def test_write_with_string_value_publishes_error(self, sensor_sim):
        """write 的 value 是字符串应被拒绝"""
        msg = self._make_msg(json.dumps({"cmd": "write", "register": 0, "value": "abc"}))
        sensor_sim.on_cmd(None, None, msg)
        assert sensor_sim.wq.empty()
        assert sensor_sim.mqtt_client.publish.called

    def test_write_with_bool_rejected(self, sensor_sim):
        """Python 里 bool 是 int 子类，应被 isinstance(int) 误判接受
        这里测实际行为：源码用 `not isinstance(reg, bool)` 防 bool 误入
        """
        msg = self._make_msg(json.dumps({"cmd": "write", "register": True, "value": 1}))
        sensor_sim.on_cmd(None, None, msg)
        # register=True 会被 isinstance(int) 接受（因为 bool 是 int），
        # 然后被 not isinstance(bool) 过滤掉
        assert sensor_sim.wq.empty()
        # 应 publish error
        assert sensor_sim.mqtt_client.publish.called

    def test_unknown_command_publishes_error(self, sensor_sim):
        msg = self._make_msg(json.dumps({"cmd": "delete_all"}))
        sensor_sim.on_cmd(None, None, msg)
        assert sensor_sim.wq.empty()
        assert sensor_sim.mqtt_client.publish.called
        payload = json.loads(sensor_sim.mqtt_client.publish.call_args.args[1])
        assert payload["type"] == "error"
        assert "未知命令" in payload["detail"]


# ---------- 6. 上报 payload 格式不变量 ----------

class TestPublishPayloadContract:
    """publish() 自动补 deviceId/ts，应符合自定义协议"""

    def _capture_publish(self, sensor_sim):
        """调 publish 并返回解析后的 payload"""
        sensor_sim.publish({"type": "test", "value": 42})
        assert sensor_sim.mqtt_client.publish.called
        # 第一次调用的 payload
        call = sensor_sim.mqtt_client.publish.call_args_list[0]
        return json.loads(call.args[1])

    def test_publish_adds_deviceId(self, sensor_sim):
        """publish 自动补 deviceId"""
        sensor_sim.device_id = "sensor_sevengroup"
        p = self._capture_publish(sensor_sim)
        assert p["deviceId"] == "sensor_sevengroup"

    def test_publish_adds_timestamp(self, sensor_sim):
        """publish 自动补 ts（ISO 格式）"""
        p = self._capture_publish(sensor_sim)
        assert "ts" in p
        # ISO 格式
        assert "T" in p["ts"] and (":" in p["ts"])

    def test_publish_does_not_overwrite_existing_deviceId(self, sensor_sim):
        """payload 自带 deviceId 时不覆盖"""
        sensor_sim.device_id = "default_device"
        sensor_sim.publish({"type": "test", "deviceId": "explicit_device", "value": 1})
        p = json.loads(sensor_sim.mqtt_client.publish.call_args_list[0].args[1])
        assert p["deviceId"] == "explicit_device"

    def test_publish_uses_topic_data(self, sensor_sim):
        """发布到 topic_data"""
        sensor_sim.topic_data = "device/sensor/sevengroup"
        sensor_sim.publish({"type": "test"})
        topic = sensor_sim.mqtt_client.publish.call_args_list[0].args[0]
        assert topic == "device/sensor/sevengroup"

    def test_publish_uses_configured_topic_cmd(self, sensor_sim):
        """命令 topic 独立于数据 topic"""
        sensor_sim.topic_data = "device/sensor/data"
        sensor_sim.topic_cmd = "device/sensor/cmd"
        sensor_sim.publish({"type": "test"})
        topic = sensor_sim.mqtt_client.publish.call_args_list[0].args[0]
        assert topic == "device/sensor/data"
        assert topic != "device/sensor/cmd"

    def test_publish_supports_retain_flag(self, sensor_sim):
        """publish 第二个参数是 retain"""
        sensor_sim.publish({"type": "online"}, retain=True)
        call = sensor_sim.mqtt_client.publish.call_args_list[0]
        assert call.kwargs.get("retain") is True

    def test_publish_default_qos_one(self, sensor_sim):
        """默认 qos=1（至少一次）"""
        sensor_sim.publish({"type": "test"})
        call = sensor_sim.mqtt_client.publish.call_args_list[0]
        assert call.kwargs.get("qos") == 1


# ---------- 7. DEFAULT_CONFIG 协议契约 ----------

class TestDefaultConfig:
    """DEFAULT_CONFIG 必须包含必要的字段"""

    def test_has_modbus_section(self, sensor_sim):
        cfg = sensor_sim.DEFAULT_CONFIG
        assert "modbus" in cfg
        for k in ("host", "port", "unit_id", "register_start", "register_count", "poll_interval"):
            assert k in cfg["modbus"], f"modbus 缺 {k}"

    def test_has_mqtt_section(self, sensor_sim):
        cfg = sensor_sim.DEFAULT_CONFIG
        assert "mqtt" in cfg
        for k in ("host", "port", "username", "password", "client_id", "topic_data", "topic_cmd"):
            assert k in cfg["mqtt"], f"mqtt 缺 {k}"

    def test_has_register_map(self, sensor_sim):
        cfg = sensor_sim.DEFAULT_CONFIG
        assert "register_map" in cfg
        # 至少应有 temperature 和 humidity
        names = [spec.get("name") for spec in cfg["register_map"].values()]
        assert "temperature" in names
        assert "humidity" in names

    def test_register_map_specs_have_required_fields(self, sensor_sim):
        """每个 register_map 项应有 name + scale + signed"""
        for offset, spec in sensor_sim.DEFAULT_CONFIG["register_map"].items():
            assert "name" in spec, f"偏移 {offset} 缺 name"
            assert "scale" in spec, f"偏移 {offset} 缺 scale"
            assert "signed" in spec, f"偏移 {offset} 缺 signed"
