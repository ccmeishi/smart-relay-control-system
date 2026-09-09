import paho.mqtt.client as mqtt
import time

got = []
def on_msg(c,u,msg):
    raw = msg.payload.decode() if msg.payload else "(empty)"
    got.append((msg.topic, raw))
    print(f"RECV [{msg.topic}] {raw[:200]}")

c = mqtt.Client(client_id="verify-sub")
c.username_pw_set("test","123456")
c.on_message = on_msg
c.connect("172.16.4.211",9783,keepalive=10)
c.subscribe("relay-cc/relaycc/#", qos=1)
c.loop_start()
print("Subscribed. Waiting 20s...")
time.sleep(20)
c.loop_stop()
print(f"Total: {len(got)} messages")
for t,r in got:
    print(f"  [{t}] {r[:150]}")
