import paho.mqtt.client as mqtt
import time
import sys

received = []
def on_message(c, u, msg):
    raw = msg.payload.decode() if msg.payload else ""
    received.append((msg.topic, raw))
    # 只打印非 loopback 的
    if 'loopback' not in raw:
        print(f"[{msg.topic}] {raw[:200]}")

def on_connect(c, u, f, rc):
    print(f"CONNECT rc={rc}, subscribing...")
    c.subscribe("relay-cc/relaycc/#", qos=1)
    print("SUBSCRIBED relay-cc/relaycc/#")
    # 也订阅虚拟产品 topic 看 Bridge 转发
    for prefix in ["lock-cc", "light-cc", "ac-cc", "sensor-cc", "human-cc", "smoke-cc"]:
        c.subscribe(f"{prefix}/#", qos=1)
    print("SUBSCRIBED all virtual products")

c = mqtt.Client(client_id="board-wait-sub")
c.username_pw_set("test", "123456")
c.on_connect = on_connect
c.on_message = on_message
c.connect("172.16.4.211", 9783, keepalive=10)

# 启动 Bridge
sys.path.insert(0, r"E:\shixiproject\traeproject1\simulator\tools")
import importlib.util
spec = importlib.util.spec_from_file_location("bridge", r"E:\shixiproject\traeproject1\simulator\tools\gateway_bridge.py")
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

c.loop_start()
print("\n=== Waiting 25s for ESP32 startup + Bridge forwarding ===")
time.sleep(25)
c.loop_stop()

print(f"\n=== Total received: {len(received)} ===")
for t, r in received:
    print(f"  [{t}] {r[:150]}")
print("DONE")
