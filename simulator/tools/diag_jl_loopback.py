"""诊断升级版: EMQX 回环测试 - 判定下行通道卡在哪一层

测试逻辑:
  1. 订阅 /sensor-cc/sensorcc/# (通配符, 能看到该设备所有 topic 的消息)
  2. 自己发布 2 条消息: 假 report + 真格式 read 请求
  3. 观察能否收回自己发的消息 (回环), 以及模拟器是否回复 read

判读:
  - 收到自己发的消息  -> test 用户发布/订阅权限正常, EMQX 通道正常
      - 但模拟器没回 read -> 模拟器订阅失效或已掉线 (检查终端有无断线日志)
  - 收不到自己发的消息 -> EMQX 层 ACL/权限问题, test 用户被限制
"""

import json
import random
import time

import paho.mqtt.client as mqtt

HOST, PORT = "172.16.4.211", 9783
BASE = "/sensor-cc/sensorcc"
TOPIC_REPORT = f"{BASE}/properties/report"
TOPIC_READ = f"{BASE}/properties/read"
TOPIC_REPLY = f"{BASE}/properties/read/reply"

received = []


def on_connect(client, _u, _f, rc):
    print(f"[连接] rc={rc}")
    result, _mid = client.subscribe(f"{BASE}/#", qos=1)
    print(f"[订阅] {BASE}/#  ->  {result} (0=成功)")


def on_message(_c, _u, msg):
    text = msg.payload.decode("utf-8", "replace")
    received.append((msg.topic, text))
    print(f"[收到] {msg.topic}")
    print(f"       {text[:120]}")


def on_disconnect(_c, _u, rc):
    print(f"[断开] rc={rc}")


client = mqtt.Client(client_id=f"diag2-jl-{random.randint(1000, 9999)}", clean_session=True)
client.username_pw_set("test", "123456")
client.on_connect = on_connect
client.on_message = on_message
client.on_disconnect = on_disconnect

print("连接 EMQX ...")
client.connect(HOST, PORT, keepalive=30)
client.loop_start()
time.sleep(2)   # 等订阅生效

# --- 回环测试: 自己发, 自己收 ---
info1 = client.publish(TOPIC_REPORT, json.dumps({"messageId": "diag-002", "properties": {"temperature": 25.0, "humidity": 50.0}}), qos=1, retain=False)
info2 = client.publish(TOPIC_READ, json.dumps({"messageId": "diag-003", "properties": ["temperature"]}), qos=1, retain=False)
info1.wait_for_publish()
info2.wait_for_publish()
print(f"[发布] 假report -> {TOPIC_REPORT}  (发送rc={info1.rc}, 已确认={info1.is_published()})")
print(f"[发布] read请求 -> {TOPIC_READ}  (发送rc={info2.rc}, 已确认={info2.is_published()})")

# 等待回环和模拟器回复
deadline = time.time() + 20
while time.time() < deadline:
    time.sleep(0.2)

print("\n================ 判读 ================")
topics = {t for t, _ in received}
self_report = any("properties/report" in t for t in topics)
self_read_reply = any("read/reply" in t for t in topics)

print(f"1) 回环收到自己发的 report : {'是 -> EMQX 通道+权限正常' if self_report else '否 -> EMQX 层 ACL/权限被限制!'}")
print(f"2) 模拟器回复了 read/reply : {'是 -> 设备在线且订阅正常' if self_read_reply else '否 -> 模拟器订阅失效或已掉线 (看终端有无断线日志)'}")

try:
    client.disconnect()
except Exception:
    pass
