"""测试 paho-mqtt 订阅是否正常工作"""
import paho.mqtt.client as mqtt
import time

def on_connect(client, userdata, flags, rc):
    print("Connected rc=", rc)
    client.subscribe("relay-cc/relaycc/#", qos=1)
    print("Subscribed relay-cc/relaycc/#")

def on_message(client, userdata, msg):
    print("RECV:", msg.topic, "->", msg.payload.decode()[:100])

def on_log(client, userdata, level, buf):
    print("LOG:", level, buf)

c = mqtt.Client("test-sub-debug")
c.username_pw_set("test", "123456")
c.on_connect = on_connect
c.on_message = on_message
c.on_log = on_log
c.connect("172.16.4.211", 9783, 60)
print("loop_start...")
c.loop_start()
time.sleep(5)
print("Publishing test message...")
c.publish("relay-cc/relaycc/properties/report", '{"test":"self-pub"}', qos=0)
time.sleep(10)
c.loop_stop()
print("DONE")
