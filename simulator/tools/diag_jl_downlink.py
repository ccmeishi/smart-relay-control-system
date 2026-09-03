"""诊断: 模拟平台下发属性读取命令, 验证设备下行链路是否完好

用法: python diag_jl_downlink.py
"""

import json
import time
import random

import paho.mqtt.client as mqtt

HOST, PORT = "172.16.4.211", 9783
TOPIC_READ = "/sensor-cc/sensorcc/properties/read"
TOPIC_REPLY = "/sensor-cc/sensorcc/properties/read/reply"

got_reply = []


def on_connect(client, _u, _f, rc):
    print(f"[连接] rc={rc}")
    client.subscribe(TOPIC_REPLY, qos=1)
    payload = {
        "messageId": "diag-001",
        "properties": ["temperature", "humidity"],
    }
    client.publish(TOPIC_READ, json.dumps(payload), qos=1, retain=False)
    print(f"[发送] -> {TOPIC_READ}")
    print(f"       {json.dumps(payload)}")


def on_message(_c, _u, msg):
    text = msg.payload.decode("utf-8", "replace")
    print(f"[回复] <- {msg.topic}")
    print(f"       {text}")
    got_reply.append(text)


def on_disconnect(_c, _u, rc):
    print(f"[断开] rc={rc}")


client = mqtt.Client(client_id=f"diag-jl-{random.randint(1000, 9999)}", clean_session=True)
client.username_pw_set("test", "123456")
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

print("连接 EMQX ...")
client.connect(HOST, PORT, keepalive=30)
client.loop_start()

deadline = time.time() + 15
while time.time() < deadline and not got_reply:
    time.sleep(0.2)

if got_reply:
    print("\n结论: 设备侧下行链路正常 (模拟器收到并回复了)")
else:
    print("\n结论: 15秒内未收到模拟器回复 -> 设备订阅/链路异常, 或命令没到设备")

try:
    client.disconnect()
except Exception:
    pass
