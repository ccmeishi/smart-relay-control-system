import paho.mqtt.client as mqtt
import time

received = []
def on_message(c, u, msg):
    raw = msg.payload.decode() if msg.payload else ""
    received.append((msg.topic, raw))
    print(f"RECV [{msg.topic}] {raw}")

c = mqtt.Client(client_id="test-loopback")
c.username_pw_set("test", "123456")
c.on_message = on_message
c.connect("172.16.4.211", 9783, keepalive=10)
c.subscribe("relay-cc/relaycc/#", qos=1)
c.loop_start()
time.sleep(1)

# 自己发一条测试
c.publish("relay-cc/relaycc/properties/report", '{"properties":{"loopback":1}}', qos=0)
print("PUBLISHED loopback test")

# 等板子的上报
print("Waiting 12s for ESP32 messages + loopback echo...")
time.sleep(12)
c.loop_stop()
print(f"\nTotal received: {len(received)}")
for t, r in received:
    print(f"  [{t}] {r[:100]}")
