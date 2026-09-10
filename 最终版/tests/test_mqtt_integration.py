"""端到端 MQTT 集成测试

启动链路：
  amqtt broker (本地) ←── gateway_bridge (monkey-patch 指向 broker) ←── paho-mqtt 测试客户端

不依赖真实 JetLinks 平台、ESP32 板子、外网。
gateway_bridge.py 源码不改，通过 conftest 里的 _run_bridge_in_thread 在 import 时
替换其 MQTT_HOST/MQTT_PORT 常量。

测试覆盖：
- 上行：模拟 ESP32 往 relay-cc/relaycc/properties/report 发 payload，验证
  bridge 拆到对应虚拟产品 topic
- 下行：模拟平台往 /light-cc/light001/properties/write 发，验证 bridge
  转发到 relay-cc/relaycc/properties/write
- 闭环：write → bridge → ESP32 reply → bridge → 平台 reply
"""
import json
import threading
import time

import pytest
import paho.mqtt.client as mqtt


# ---------- 工具：paho-mqtt 客户端工厂 ----------

def _make_client(client_id: str, broker: dict, on_message=None):
    """创建 paho-mqtt 客户端，连接并 loop_start，返回 client"""
    c = mqtt.Client(client_id=client_id, clean_session=True)
    c.connect(broker["host"], broker["port"], keepalive=30)
    if on_message is not None:
        c.on_message = on_message
    c.loop_start()
    # 等连接就绪
    deadline = time.time() + 3.0
    while time.time() < deadline and not c.is_connected():
        time.sleep(0.05)
    if not c.is_connected():
        raise RuntimeError(f"paho-mqtt 客户端 {client_id} 连接 broker 失败")
    return c


class _TopicCollector:
    """订阅一组 topic，收集所有消息（线程安全）"""

    def __init__(self, client, topics, qos=1):
        self.client = client
        self.topics = topics
        self.received = []  # [(topic, payload_dict), ...]
        self._lock = threading.Lock()
        self._event = threading.Event()

        def on_message(_client, _userdata, msg):
            try:
                payload = json.loads(msg.payload.decode())
            except Exception:
                payload = {"_raw": msg.payload.decode(errors="replace")}
            with self._lock:
                self.received.append((msg.topic, payload))
            self._event.set()

        self._on_message = on_message
        self.client.on_message = on_message
        for t in topics:
            self.client.subscribe(t, qos=qos)

    def wait_for(self, predicate, timeout=3.0):
        """等待直到收到满足 predicate(topic, payload) 的消息"""
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._event.clear()
            with self._lock:
                msgs = list(self.received)
            for t, p in msgs:
                if predicate(t, p):
                    return (t, p)
            self._event.wait(timeout=0.2)
        raise AssertionError(f"在 {timeout}s 内未收到满足条件的消息 (已收 {len(self.received)} 条)")

    def all_received(self):
        with self._lock:
            return list(self.received)


@pytest.fixture
def esp32_simulator(bridge_under_test):
    """模拟 ESP32 网关：连 broker，可发布/订阅

    yield paho-mqtt 客户端（扮演 ESP32 角色）
    """
    c = _make_client("esp32-sim", bridge_under_test["broker"])
    try:
        yield c
    finally:
        try:
            c.loop_stop()
            c.disconnect()
        except Exception:
            pass


@pytest.fixture
def platform_simulator(bridge_under_test):
    """模拟 JetLinks 平台：连 broker，可发布/订阅"""
    c = _make_client("platform-sim", bridge_under_test["broker"])
    try:
        yield c
    finally:
        try:
            c.loop_stop()
            c.disconnect()
        except Exception:
            pass


# ---------- 1. 上行：ESP32 report → Bridge 拆分 ----------

class TestUplinkEndToEnd:
    """模拟 ESP32 上报，验证 bridge 拆分到虚拟产品"""

    def test_relay1_report_routed_to_lock(self, bridge_under_test, esp32_simulator, platform_simulator):
        """relay1=1 应在 /lock-cc/lock001/properties/report 收到 switch=1"""
        collector = _TopicCollector(platform_simulator, [
            "/lock-cc/lock001/properties/report",
        ])

        # ESP32 上报
        esp32_simulator.publish(
            "relay-cc/relaycc/properties/report",
            json.dumps({
                "timestamp": 1000000,
                "messageId": "esp-msg-1",
                "properties": {"relay1": 1},
            }),
            qos=1,
        )

        topic, payload = collector.wait_for(
            lambda t, p: "lock" in t,
            timeout=3.0,
        )
        assert topic == "/lock-cc/lock001/properties/report"
        assert payload["properties"] == {"switch": 1}
        # messageId 应携带来源信息
        assert "esp-msg-1" in payload["messageId"]

    def test_temperature_humidity_merged_to_sensor(self, bridge_under_test, esp32_simulator, platform_simulator):
        """temperature+humidity 应合并到 /sensor-cc/sensorcc 同一 report"""
        collector = _TopicCollector(platform_simulator, [
            "/sensor-cc/sensorcc/properties/report",
        ])

        esp32_simulator.publish(
            "relay-cc/relaycc/properties/report",
            json.dumps({
                "timestamp": 2000000,
                "messageId": "esp-msg-2",
                "properties": {"temperature": 25.5, "humidity": 60.0},
            }),
            qos=1,
        )

        topic, payload = collector.wait_for(
            lambda t, p: "sensor" in t,
            timeout=3.0,
        )
        assert topic == "/sensor-cc/sensorcc/properties/report"
        assert payload["properties"] == {"temperature": 25.5, "humidity": 60.0}

    def test_multi_relay_split_to_multiple_virtuals(self, bridge_under_test, esp32_simulator, platform_simulator):
        """relay1~4 拆分到 4 个不同虚拟设备"""
        collector = _TopicCollector(platform_simulator, [
            "/lock-cc/lock001/properties/report",
            "/light-cc/light001/properties/report",
            "/light-cc/light002/properties/report",
            "/ac-cc/ac001/properties/report",
        ])

        esp32_simulator.publish(
            "relay-cc/relaycc/properties/report",
            json.dumps({
                "timestamp": 3000000,
                "messageId": "esp-msg-3",
                "properties": {"relay1": 1, "relay2": 0, "relay3": 1, "relay4": 0},
            }),
            qos=1,
        )

        # 等全部 4 个
        deadline = time.time() + 3.0
        while time.time() < deadline:
            msgs = [t for t, _ in collector.all_received()]
            if len(msgs) >= 4:
                break
            time.sleep(0.1)
        msgs = collector.all_received()
        topics = {t for t, _ in msgs}
        assert "/lock-cc/lock001/properties/report" in topics
        assert "/light-cc/light001/properties/report" in topics
        assert "/light-cc/light002/properties/report" in topics
        assert "/ac-cc/ac001/properties/report" in topics

        # 验证值正确
        by_topic = {t: p for t, p in msgs}
        assert by_topic["/lock-cc/lock001/properties/report"]["properties"] == {"switch": 1}
        assert by_topic["/light-cc/light001/properties/report"]["properties"] == {"switch": 0}
        assert by_topic["/light-cc/light002/properties/report"]["properties"] == {"switch": 1}
        assert by_topic["/ac-cc/ac001/properties/report"]["properties"] == {"switch": 0}

    def test_unknown_gateway_key_ignored(self, bridge_under_test, esp32_simulator, platform_simulator):
        """未配的 gateway key 不应转发"""
        collector = _TopicCollector(platform_simulator, [
            "/lock-cc/lock001/properties/report",
        ])

        esp32_simulator.publish(
            "relay-cc/relaycc/properties/report",
            json.dumps({
                "timestamp": 4000000,
                "messageId": "esp-msg-4",
                "properties": {"relay1": 1, "unknown_key": 42},
            }),
            qos=1,
        )

        topic, payload = collector.wait_for(
            lambda t, p: "lock" in t,
            timeout=3.0,
        )
        # 只应有 switch=1，不应包含 unknown_key
        assert payload["properties"] == {"switch": 1}


# ---------- 2. 下行：平台 write → Bridge 转发到网关 ----------

class TestDownlinkEndToEnd:
    """模拟平台下发 write，验证 bridge 转发到网关"""

    def test_platform_write_routes_to_gateway(self, bridge_under_test, esp32_simulator, platform_simulator):
        """平台对 /light-cc/light001/properties/write switch=1 应被转发到
        relay-cc/relaycc/properties/write 携带 relay2=1
        """
        collector = _TopicCollector(esp32_simulator, [
            "relay-cc/relaycc/properties/write",
        ])

        platform_simulator.publish(
            "/light-cc/light001/properties/write",
            json.dumps({
                "timestamp": 5000000,
                "messageId": "platform-cmd-1",
                "properties": {"switch": 1},
            }),
            qos=1,
        )

        topic, payload = collector.wait_for(
            lambda t, p: "properties/write" in t and "relay-cc" in t,
            timeout=3.0,
        )
        assert topic == "relay-cc/relaycc/properties/write"
        assert payload["properties"] == {"relay2": 1}
        # messageId 已被替换为 bridge 生成的 id
        assert payload["messageId"] != "platform-cmd-1"
        assert payload["messageId"].startswith("bridge-")

    def test_platform_invoke_routes_to_gateway(self, bridge_under_test, esp32_simulator, platform_simulator):
        """invoke 透传到 gateway"""
        collector = _TopicCollector(esp32_simulator, [
            "relay-cc/relaycc/function/invoke",
        ])

        platform_simulator.publish(
            "/ac-cc/ac001/function/invoke",
            json.dumps({
                "timestamp": 6000000,
                "messageId": "platform-inv-1",
                "functionId": "set_temp",
                "inputs": {"target": 26},
            }),
            qos=1,
        )

        topic, payload = collector.wait_for(
            lambda t, p: "function/invoke" in t,
            timeout=3.0,
        )
        assert topic == "relay-cc/relaycc/function/invoke"
        assert payload["functionId"] == "set_temp"
        assert payload["inputs"] == {"target": 26}


# ---------- 3. 端到端闭环：write → 网关 reply → 平台 reply ----------

class TestEndToEndLoop:
    """完整 write → reply 闭环"""

    def test_write_then_reply_routed_back(self, bridge_under_test, esp32_simulator, platform_simulator):
        """完整流程：
        1. 平台 write → bridge 转发 → ESP32 收到
        2. ESP32 reply → bridge 路由回 → 平台收到（用原始 messageId）
        """
        # 1. 平台订阅自己的 reply topic
        platform_collector = _TopicCollector(platform_simulator, [
            "/light-cc/light001/write_reply",
        ])
        # 2. ESP32 订阅网关的 write topic
        esp32_collector = _TopicCollector(esp32_simulator, [
            "relay-cc/relaycc/properties/write",
        ])

        # Step 1: 平台对 light-cc 下发 write
        platform_simulator.publish(
            "/light-cc/light001/properties/write",
            json.dumps({
                "timestamp": 7000000,
                "messageId": "platform-final-cmd",
                "properties": {"switch": 1},
            }),
            qos=1,
        )

        # 等 ESP32 收到 write
        _, write_payload = esp32_collector.wait_for(
            lambda t, p: "relay-cc" in t,
            timeout=3.0,
        )
        bridge_mid = write_payload["messageId"]
        assert write_payload["properties"] == {"relay2": 1}

        # Step 2: 模拟 ESP32 网关发 reply
        time.sleep(0.2)  # 让 bridge 把 messageId 映射稳定
        esp32_simulator.publish(
            "relay-cc/relaycc/properties/write/reply",
            json.dumps({
                "timestamp": 7100000,
                "messageId": bridge_mid,
                "successful": True,
            }),
            qos=1,
        )

        # 等平台收到 reply
        _, reply_payload = platform_collector.wait_for(
            lambda t, p: "write_reply" in t,
            timeout=3.0,
        )
        # messageId 应恢复为平台原始 ID
        assert reply_payload["messageId"] == "platform-final-cmd"
        assert reply_payload["successful"] is True
        # topic 实际是 /light-cc/light001/write_reply（不是 properties/write/reply）
        # 这是源码当前实现，详见 gateway_bridge.py 的 TODO 注释
        # 若以后按 JetLinks 标准改，这里需要更新断言
        assert platform_collector.received[-1][0] == "/light-cc/light001/write_reply"
