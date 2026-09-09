import paho.mqtt.client as mqtt
import time

def on_connect(c, u, f, rc):
    print(f"CONNECT rc={rc}")
    c.subscribe("relay-cc/relaycc/#", qos=1)
    print("SUBSCRIBED relay-cc/relaycc/#")

def on_message(c, u, msg):
    raw = msg.payload.decode() if msg.payload else ""
    print(f"[{msg.topic}] ({len(raw)}B) {raw[:120]}")

c = mqtt.Client(client_id="simple-sub-test")
c.username_pw_set("test", "123456")
c.on_connect = on_connect
c.on_message = on_message
c.connect("172.16.4.211", 9783, keepalive=10)
print("Waiting 15s for messages...")
c.loop_start()
time.sleep(15)
c.loop_stop()
print("DONE")
