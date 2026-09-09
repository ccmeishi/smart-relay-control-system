"""gateway_bridge.py 单元 + 集成测试

覆盖的路由逻辑（来自源码）：
上行（ESP32 网关 → 6 个虚拟产品）：
  relay1      → lock-cc  / lock001  (switch)
  relay2      → light-cc / light001 (switch)
  relay3      → light-cc / light002 (switch)
  relay4      → ac-cc    / ac001    (switch)
  temperature → sensor-cc/ sensorcc (temperature)
  humidity    → sensor-cc/ sensorcc (humidity)
  human       → human-cc / human001 (detected)
  smoke       → smoke-cc / smoke001 (level)
  current     → sensor-cc/ sensorcc (current)
  voltage     → sensor-cc/ sensorcc (voltage)

下行（虚拟产品 → ESP32 网关）：
  虚拟产品 property → 路由回对应 gateway relay key

messageId 闭环：
  下行时 Bridge 生成新 mid (bridge_mid)，记录 (origin_product, origin_msg_id) → bridge_mid
  网关 reply 到来时用 bridge_mid 找回 origin，再用 origin_msg_id 回复虚拟产品
"""
import importlib
import json
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest


# 找到 gateway_bridge.py
GATEWAY_BRIDGE_PATH = (
    Path(__file__).resolve().parent.parent / "tools" / "gateway_bridge.py"
)
TOOLS_DIR = str(GATEWAY_BRIDGE_PATH.parent)


@pytest.fixture
def bridge_module():
    """导入 gateway_bridge 模块（每次重新加载以隔离状态）

    - 加 tools/ 到 sys.path
    - 替换 _BRIDGE_PUBLISHER 为 MagicMock（让 publish 不真的发 MQTT）
    - 清理 _msg_map
    """
    if TOOLS_DIR not in sys.path:
        sys.path.insert(0, TOOLS_DIR)
    # 重新加载以隔离 module-level 状态
    if "gateway_bridge" in sys.modules:
        importlib.reload(sys.modules["gateway_bridge"])
    import gateway_bridge as gb

    # 替换 publisher 为 mock，捕获所有 publish 调用
    gb._BRIDGE_PUBLISHER = MagicMock()
    # 清空 messageId 映射
    gb._msg_map.clear()
    return gb


# ---------- 1. 路由表自洽性 ----------

class TestRoutingTables:
    """UP_ROUTING / DOWN_ROUTING / VIRTUAL_* 必须自洽"""

    def test_up_routing_has_all_expected_keys(self, bridge_module):
        """UP_ROUTING 至少包含 8 个 key"""
        gb = bridge_module
        for key in [
            "relay1", "relay2", "relay3", "relay4",
            "temperature", "humidity", "human", "smoke",
        ]:
            assert key in gb.UP_ROUTING, f"UP_ROUTING 缺 {key}"

    def test_down_routing_is_inverse_of_up(self, bridge_module):
        """DOWN_ROUTING[(product, device, property)] == gateway_key 必须与 UP_ROUTING 反向一致"""
        gb = bridge_module
        for gw_key, info in gb.UP_ROUTING.items():
            rev_key = (info["product"], info["device"], info["property"])
            assert rev_key in gb.DOWN_ROUTING
            assert gb.DOWN_ROUTING[rev_key] == gw_key

    def test_virtual_products_unique(self, bridge_module):
        """VIRTUAL_PRODUCTS 不能有重复"""
        gb = bridge_module
        assert len(gb.VIRTUAL_PRODUCTS) == len(set(gb.VIRTUAL_PRODUCTS))

    def test_virtual_devices_consistent(self, bridge_module):
        """VIRTUAL_DEVICES 的 key 集合应等于 VIRTUAL_PRODUCTS 集合"""
        gb = bridge_module
        assert set(gb.VIRTUAL_DEVICES.keys()) == set(gb.VIRTUAL_PRODUCTS)

    def test_each_virtual_product_has_at_least_one_device(self, bridge_module):
        """每个虚拟产品至少 1 个设备"""
        gb = bridge_module
        for product, devices in gb.VIRTUAL_DEVICES.items():
            assert len(devices) >= 1, f"{product} 没设备"


# ---------- 2. 主题构造 ----------

class TestTopics:
    """topic 构造和 gateway topics"""

    def test_virtual_topic_with_leading_slash(self, bridge_module):
        """虚拟产品 topic 必须带前导 /"""
        gb = bridge_module
        assert gb.virtual_topic("light-cc", "light001", "properties/report") == \
               "/light-cc/light001/properties/report"

    def test_gateway_topics_keys(self, bridge_module):
        """GATEWAY_TOPICS 应包含 7 个标准 topic"""
        gb = bridge_module
        for key in ("report", "event", "write", "write_reply",
                    "read", "read_reply", "invoke", "invoke_reply"):
            assert key in gb.GATEWAY_TOPICS
        assert gb.GATEWAY_TOPICS["report"] == "relay-cc/relaycc/properties/report"
        assert gb.GATEWAY_TOPICS["write"] == "relay-cc/relaycc/properties/write"


# ---------- 3. 上行：网关 report → 拆分到虚拟产品 ----------

class TestUplinkSplit:
    """handle_gateway_properties_report 拆分逻辑"""

    def test_split_relay_to_virtual(self, bridge_module):
        """relay1=1 应拆到 lock-cc/lock001 的 switch 属性"""
        gb = bridge_module
        gb.handle_gateway_properties_report({
            "timestamp": 1000,
            "messageId": "esp-msg-1",
            "properties": {"relay1": 1},
        })
        gb._BRIDGE_PUBLISHER.publish.assert_called_once()
        call = gb._BRIDGE_PUBLISHER.publish.call_args
        topic = call.args[0]
        payload_str = call.args[1]
        assert topic == "/lock-cc/lock001/properties/report"
        payload = json.loads(payload_str)
        assert payload["properties"] == {"switch": 1}
        assert "lock-cc" in payload["messageId"]
        assert "lock001" in payload["messageId"]

    def test_split_temperature_humidity_to_same_device(self, bridge_module):
        """temperature + humidity 应合并到同一 sensor-cc/sensorcc 设备的 2 个属性"""
        gb = bridge_module
        gb.handle_gateway_properties_report({
            "timestamp": 2000,
            "messageId": "esp-msg-2",
            "properties": {"temperature": 26.5, "humidity": 60.0},
        })
        # 只应该调 1 次 publish（因为同一设备）
        assert gb._BRIDGE_PUBLISHER.publish.call_count == 1
        call = gb._BRIDGE_PUBLISHER.publish.call_args
        topic = call.args[0]
        payload_str = call.args[1]
        assert topic == "/sensor-cc/sensorcc/properties/report"
        payload = json.loads(payload_str)
        assert payload["properties"] == {"temperature": 26.5, "humidity": 60.0}

    def test_split_multiple_relays_to_multiple_devices(self, bridge_module):
        """relay1~4 拆分到 4 个不同虚拟设备"""
        gb = bridge_module
        gb.handle_gateway_properties_report({
            "timestamp": 3000,
            "messageId": "esp-msg-3",
            "properties": {"relay1": 1, "relay2": 0, "relay3": 1, "relay4": 0},
        })
        # 应发 4 次 publish
        assert gb._BRIDGE_PUBLISHER.publish.call_count == 4
        topics = [call.args[0] for call in gb._BRIDGE_PUBLISHER.publish.call_args_list]
        assert "/lock-cc/lock001/properties/report" in topics
        assert "/light-cc/light001/properties/report" in topics
        assert "/light-cc/light002/properties/report" in topics
        assert "/ac-cc/ac001/properties/report" in topics

    def test_unknown_gateway_key_skipped(self, bridge_module):
        """未配置的 key 应被忽略，不应让 publish 失败"""
        gb = bridge_module
        gb.handle_gateway_properties_report({
            "timestamp": 4000,
            "messageId": "esp-msg-4",
            "properties": {"relay1": 1, "unknown_key": 42},
        })
        # 只应为 relay1 发 1 次
        assert gb._BRIDGE_PUBLISHER.publish.call_count == 1

    def test_empty_properties_does_not_publish(self, bridge_module):
        """properties 为空（全部 unknown）不应 publish"""
        gb = bridge_module
        gb.handle_gateway_properties_report({
            "timestamp": 5000,
            "messageId": "esp-msg-5",
            "properties": {"foo": 1, "bar": 2},
        })
        gb._BRIDGE_PUBLISHER.publish.assert_not_called()

    def test_messageId_propagation(self, bridge_module):
        """拆分到虚拟产品时 messageId 应带上原 mid 后缀"""
        gb = bridge_module
        gb.handle_gateway_properties_report({
            "timestamp": 6000,
            "messageId": "original-mid-123",
            "properties": {"relay1": 1, "relay2": 0},
        })
        for call in gb._BRIDGE_PUBLISHER.publish.call_args_list:
            payload = json.loads(call.args[1])
            assert payload["messageId"].startswith("original-mid-123-")
            assert "lock-cc" in payload["messageId"] or "light-cc" in payload["messageId"]


# ---------- 4. 下行：虚拟 write → 网关 write ----------

class TestDownlinkWrite:
    """handle_virtual_write 路由回网关"""

    def test_light_switch_to_relay2(self, bridge_module):
        """对 light-cc/light001 的 switch=1 应变成 gateway relay2=1"""
        gb = bridge_module
        gb.handle_virtual_write("light-cc", "light001", {
            "timestamp": 7000,
            "messageId": "platform-msg-1",
            "properties": {"switch": 1},
        })
        gb._BRIDGE_PUBLISHER.publish.assert_called_once()
        call = gb._BRIDGE_PUBLISHER.publish.call_args
        topic = call.args[0]
        payload_str = call.args[1]
        assert topic == "relay-cc/relaycc/properties/write"
        payload = json.loads(payload_str)
        assert payload["properties"] == {"relay2": 1}
        # messageId 映射应记录
        assert len(gb._msg_map) == 1

    def test_ac_switch_to_relay4(self, bridge_module):
        """ac-cc/ac001 switch → relay4"""
        gb = bridge_module
        gb.handle_virtual_write("ac-cc", "ac001", {
            "timestamp": 7100,
            "messageId": "platform-msg-2",
            "properties": {"switch": 0},
        })
        payload = json.loads(gb._BRIDGE_PUBLISHER.publish.call_args.args[1])
        assert payload["properties"] == {"relay4": 0}

    def test_unmapped_property_ignored(self, bridge_module):
        """虚拟产品的属性如果没在 DOWN_ROUTING 中（未配的），应被忽略"""
        gb = bridge_module
        gb.handle_virtual_write("light-cc", "light001", {
            "timestamp": 7200,
            "messageId": "platform-msg-3",
            "properties": {"switch": 1, "brightness": 50},  # brightness 没配
        })
        # 仍然发，但只发 switch（转成 relay2）
        payload = json.loads(gb._BRIDGE_PUBLISHER.publish.call_args.args[1])
        # brightness 没有 DOWN_ROUTING，被丢弃
        assert "brightness" not in payload["properties"]
        # switch → relay2
        assert payload["properties"] == {"relay2": 1}

    def test_no_valid_property_does_not_publish(self, bridge_module):
        """所有 property 都没路由 → 不发 publish"""
        gb = bridge_module
        gb.handle_virtual_write("light-cc", "light001", {
            "timestamp": 7300,
            "messageId": "platform-msg-4",
            "properties": {"nonexistent_prop": 99},
        })
        gb._BRIDGE_PUBLISHER.publish.assert_not_called()

    def test_messageId_mapping_recorded(self, bridge_module):
        """下行时应记录 (origin_product, origin_msg_id) → bridge_msg_id"""
        gb = bridge_module
        gb.handle_virtual_write("light-cc", "light001", {
            "timestamp": 7400,
            "messageId": "platform-orig-msg-xyz",
            "properties": {"switch": 1},
        })
        # _msg_map 应有 1 条
        assert len(gb._msg_map) == 1
        entry = list(gb._msg_map.values())[0]
        assert entry["origin_product"] == "light-cc"
        assert entry["origin_device"] == "light001"
        assert entry["origin_msg_id"] == "platform-orig-msg-xyz"
        assert entry["reply_key"] == "write_reply"


# ---------- 5. 下行：虚拟 invoke → 网关 invoke ----------

class TestDownlinkInvoke:
    """handle_virtual_invoke 路由回网关"""

    def test_invoke_with_functionId(self, bridge_module):
        """普通 functionId 应透传到网关 invoke"""
        gb = bridge_module
        gb.handle_virtual_invoke("light-cc", "light001", {
            "timestamp": 8000,
            "messageId": "invoke-msg-1",
            "functionId": "set_brightness",
            "inputs": {"level": 50},
        })
        call = gb._BRIDGE_PUBLISHER.publish.call_args
        topic = call.args[0]
        payload_str = call.args[1]
        assert topic == "relay-cc/relaycc/function/invoke"
        payload = json.loads(payload_str)
        assert payload["functionId"] == "set_brightness"
        assert payload["inputs"] == {"level": 50}

    def test_invoke_with_functionId_write_routes_to_write(self, bridge_module):
        """functionId='write' 的 invoke 应走和 properties/write 一样的路径"""
        gb = bridge_module
        gb.handle_virtual_invoke("light-cc", "light001", {
            "timestamp": 8100,
            "messageId": "invoke-write-msg",
            "functionId": "write",
            "inputs": {"switch": 1},
        })
        # 应发到 properties/write 而不是 function/invoke
        call = gb._BRIDGE_PUBLISHER.publish.call_args
        topic = call.args[0]
        assert topic == "relay-cc/relaycc/properties/write"
        payload = json.loads(call.args[1])
        assert payload["properties"] == {"relay2": 1}

    def test_invoke_with_list_inputs(self, bridge_module):
        """inputs 是 list 格式（JetLinks 有时这样）应能处理"""
        gb = bridge_module
        gb.handle_virtual_invoke("light-cc", "light001", {
            "timestamp": 8200,
            "messageId": "invoke-list-msg",
            "functionId": "set_color",
            "inputs": [
                {"name": "r", "value": 255},
                {"name": "g", "value": 0},
            ],
        })
        payload = json.loads(gb._BRIDGE_PUBLISHER.publish.call_args.args[1])
        assert payload["inputs"] == {"r": 255, "g": 0}


# ---------- 6. 网关 reply → 虚拟设备 reply ----------

class TestReplyRouting:
    """handle_gateway_reply messageId 闭环"""

    def test_write_reply_routes_back_to_origin(self, bridge_module):
        """网关 write_reply 应回到发起 write 的虚拟设备"""
        gb = bridge_module
        # 1. 平台对 light-cc 下发 write
        gb.handle_virtual_write("light-cc", "light001", {
            "timestamp": 9000,
            "messageId": "platform-write-1",
            "properties": {"switch": 1},
        })
        # 2. 抓到发给网关的 bridge_msg_id
        call = gb._BRIDGE_PUBLISHER.publish.call_args
        bridge_mid = json.loads(call.args[1])["messageId"]
        # 3. 模拟网关 reply（用 bridge_mid）
        gb._BRIDGE_PUBLISHER.publish.reset_mock()
        gb.handle_gateway_reply("write_reply", {
            "timestamp": 9100,
            "messageId": bridge_mid,
            "successful": True,
        })
        # 4. 应发到 light-cc 的 write_reply topic
        # 注：源码里 reply_key 直接当 suffix 拼到 virtual_topic，
        #     所以 topic 是 /light-cc/light001/write_reply（不是 properties/write/reply）
        call = gb._BRIDGE_PUBLISHER.publish.call_args
        topic = call.args[0]
        payload_str = call.args[1]
        assert topic == "/light-cc/light001/write_reply"
        payload = json.loads(payload_str)
        assert payload["messageId"] == "platform-write-1"  # 用的是 origin_msg_id
        assert payload["successful"] is True

    def test_invoke_reply_routes_back_to_origin(self, bridge_module):
        """invoke reply 也应正确路由"""
        gb = bridge_module
        gb.handle_virtual_invoke("ac-cc", "ac001", {
            "timestamp": 9200,
            "messageId": "platform-invoke-1",
            "functionId": "set_temp",
            "inputs": {"target": 26},
        })
        call = gb._BRIDGE_PUBLISHER.publish.call_args
        bridge_mid = json.loads(call.args[1])["messageId"]
        gb._BRIDGE_PUBLISHER.publish.reset_mock()
        gb.handle_gateway_reply("invoke_reply", {
            "timestamp": 9300,
            "messageId": bridge_mid,
            "successful": True,
            "output": {"current_temp": 26.5},
        })
        topic = gb._BRIDGE_PUBLISHER.publish.call_args.args[0]
        # 同上，reply_key 直接当 suffix
        assert topic == "/ac-cc/ac001/invoke_reply"

    def test_reply_without_mapping_silently_dropped(self, bridge_module):
        """没有映射的 reply（孤儿 reply）应被忽略，不抛异常"""
        gb = bridge_module
        gb._BRIDGE_PUBLISHER.publish.reset_mock()
        gb.handle_gateway_reply("write_reply", {
            "timestamp": 9400,
            "messageId": "unmapped-msg",
            "successful": True,
        })
        gb._BRIDGE_PUBLISHER.publish.assert_not_called()


# ---------- 7. 消息映射清理 ----------

class TestMessageIdMapping:
    """_msg_map 容量限制和过期清理"""

    def test_msg_map_capped_at_200(self, bridge_module):
        """超过 200 条后应淘汰到 150（源码：>200 时淘汰到 150）"""
        gb = bridge_module
        # 注入 300 条，全部时间戳都新鲜
        for i in range(300):
            gb._store_reply_mapping("p", "d", "write_reply", f"id-{i}", f"orig-{i}")
        # 源码逻辑：> 200 时淘汰到 150，所以上限 = 200（下一次插入会变成 201）
        # 但插入 300 次后，应该早就被截到 200 左右
        # 最后一次插入后，len 可能是 200（刚截完）或 201
        assert len(gb._msg_map) <= 201, f"msg_map 没被截流: {len(gb._msg_map)}"

    def test_msg_map_clears_stale(self, bridge_module):
        """超过 30 秒的应被清理"""
        gb = bridge_module
        gb._store_reply_mapping("p", "d", "write_reply", "old-id", "orig-old")
        # 手动把时间改到 31 秒前
        gb._msg_map["old-id"]["ts"] -= 31
        # 下一次 store 应触发清理
        gb._store_reply_mapping("p", "d", "write_reply", "new-id", "orig-new")
        assert "old-id" not in gb._msg_map
        assert "new-id" in gb._msg_map


# ---------- 8. 端到端流程（mock 全链路） ----------

class TestEndToEndMock:
    """模拟完整一次上下行闭环"""

    def test_platform_turns_on_light_via_bridge(self, bridge_module):
        """平台下发开灯 → Bridge 拆给 relay2 → 模拟网关 reply → Bridge 回写 reply"""
        gb = bridge_module

        # Step 1: 平台对 light-cc/light001 下发 switch=1
        gb.handle_virtual_write("light-cc", "light001", {
            "timestamp": 10000,
            "messageId": "cmd-001",
            "properties": {"switch": 1},
        })
        write_call = gb._BRIDGE_PUBLISHER.publish.call_args
        write_topic = write_call.args[0]
        write_payload = json.loads(write_call.args[1])
        assert write_topic == "relay-cc/relaycc/properties/write"
        assert write_payload["properties"] == {"relay2": 1}
        bridge_mid = write_payload["messageId"]

        # Step 2: 模拟 ESP32 网关收到并回复 reply
        gb._BRIDGE_PUBLISHER.publish.reset_mock()
        gb.handle_gateway_reply("write_reply", {
            "timestamp": 10100,
            "messageId": bridge_mid,
            "successful": True,
        })

        # Step 3: 验证 Bridge 已把 reply 转回 light-cc
        reply_call = gb._BRIDGE_PUBLISHER.publish.call_args
        # 注：源码 reply topic 是 /product/device/{reply_key}，不是 properties/write/reply
        assert reply_call.args[0] == "/light-cc/light001/write_reply"
        reply_payload = json.loads(reply_call.args[1])
        assert reply_payload["messageId"] == "cmd-001"  # 原始 platform messageId

    def test_sensor_report_then_virtual_subscribers_get_data(self, bridge_module):
        """ESP32 上报温湿度 → 拆给 sensor-cc → 平台看到 sensor-cc 的属性"""
        gb = bridge_module

        # Step 1: 网关上报
        gb.handle_gateway_properties_report({
            "timestamp": 11000,
            "messageId": "esp-batch-1",
            "properties": {
                "temperature": 25.3,
                "humidity": 60.5,
                "relay1": 1,
            },
        })

        # Step 2: 应该有 2 次 publish（1 个 sensor + 1 个 lock）
        assert gb._BRIDGE_PUBLISHER.publish.call_count == 2
        topics = [c.args[0] for c in gb._BRIDGE_PUBLISHER.publish.call_args_list]
        payloads = {c.args[0]: json.loads(c.args[1]) for c in gb._BRIDGE_PUBLISHER.publish.call_args_list}

        # sensor-cc 收到 temperature + humidity
        assert "/sensor-cc/sensorcc/properties/report" in topics
        sensor_props = payloads["/sensor-cc/sensorcc/properties/report"]["properties"]
        assert sensor_props == {"temperature": 25.3, "humidity": 60.5}

        # lock-cc 收到 relay1=1 → switch=1
        assert "/lock-cc/lock001/properties/report" in topics
        lock_props = payloads["/lock-cc/lock001/properties/report"]["properties"]
        assert lock_props == {"switch": 1}
