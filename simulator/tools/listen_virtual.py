import paho.mqtt.client as mqtt
import time

msgs = []

def on_connect(client, userdata, flags, rc):
    print("Connected rc=", rc)
    # 订阅所有虚拟产品
    topics = [
        "lock-cc/lock001/#",
        "light-cc/light001/#",
        "light-cc/light002/#",
        "ac-cc/ac001/#",
        "sensor-cc/sensorcc/#",
        "human-cc/human001/#",
        "smoke-cc/smoke001/#",
    ]
    for t in topics:
        client.subscribe(t, qos=1)
    print("Subscribed all virtual products")

def on_message(client, userdata, message):
    payload = message.payload.decode("utf-8", errors="replace")
    msgs.append((message.topic, payload))
    print("VIRTUAL RECV [%s] -> %s" % (message.topic, payload[:150]))

c = mqtt.Client("pc-virtual-listener")
c.username_pw_set("test", "123456")
c.on_connect = on_connect
c.on_message = on_message
c.connect("172.16.4.211", 9783, 60)
c.loop_start()
print("Listening 40s for virtual product messages...")
time.sleep(40)
c.loop_stop()
print("\nTotal virtual messages:", len(msgs))
