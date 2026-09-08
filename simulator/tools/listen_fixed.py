import paho.mqtt.client as mqtt
import time

msgs = []

def on_connect(client, userdata, flags, rc):
    print("Connected rc=", rc)
    client.subscribe("relay-cc/relaycc/#")
    print("Subscribed relay-cc/relaycc/#")

def on_message(client, userdata, message):
    payload = message.payload.decode("utf-8", errors="replace")
    msgs.append((message.topic, payload))
    print("PC RECV [%s] -> %s" % (message.topic, payload[:150]))

c = mqtt.Client("pc-listener-fixed")
c.username_pw_set("test", "123456")
c.on_connect = on_connect
c.on_message = on_message
c.connect("172.16.4.211", 9783, 60)
c.loop_start()
print("Listening 30s...")
time.sleep(30)
c.loop_stop()
print("\nTotal received:", len(msgs))
