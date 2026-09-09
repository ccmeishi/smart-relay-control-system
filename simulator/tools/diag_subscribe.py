"""快速 MQTT 诊断脚本: 订阅 relay-cc/# 和 diag/#, 打印所有收到的"""
import paho.mqtt.client as mqtt
import time

GOT = {"relay": [], "diag": []}

def on_message(client, userdata, msg):
    topic = msg.topic
    try:
        body = msg.payload.decode()
    except Exception:
        body = repr(msg.payload)
    ts = time.strftime("%H:%M:%S")
    marker = ""
    if "relay-cc" in topic:
        marker = "★RELAY"
        GOT["relay"].append((topic, body))
    elif "diag" in topic:
        marker = "★DIAG"
        GOT["diag"].append((topic, body))
    print(f"[{ts}] {marker} topic={topic}")
    if body:
        print(f"         body={body[:120]}")

c = mqtt.Client("diag-subscriber-001")
c.username_pw_set("test", "123456")
c.on_message = on_message
c.connect("172.16.4.211", 9783, keepalive=10)

# 订阅两个精确 topic
c.subscribe("relay-cc/relaycc/#", qos=0)
c.subscribe("/relay-cc/relaycc/#", qos=0)
c.subscribe("diag/#", qos=0)

print("订阅启动! 按 Ctrl+C 退出")
print("=" * 50)
c.loop_start()

# 主动发一条 marker
time.sleep(1)
pub = mqtt.Client("diag-publisher-002")
pub.username_pw_set("test", "123456")
pub.connect("172.16.4.211", 9783)
pub.publish("diag/pc-sent", "marker-line-ok", qos=0)
pub.disconnect()
print("[OK] 我刚发了 diag/pc-sent marker, 如果没看到就是 broker 过滤了")

try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n===== 汇总 =====")
    print(f"relay-cc 消息: {len(GOT['relay'])} 条")
    print(f"diag 消息: {len(GOT['diag'])} 条")
    if GOT['relay']:
        print("\n前 3 条 relay 消息:")
        for t, b in GOT['relay'][:3]:
            print(f"  {t} -> {b[:100]}")
