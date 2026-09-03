"""诊断: 全程监听 /sensor-cc/sensorcc/# 并主动触发, 精确判定哪些消息能到 EMQX
时间线: +5s 写reg1触发report | +15s 发read | +25s 还原 | +32s 结束汇总
"""

import json
import time
import random

from pymodbus.client import ModbusTcpClient
import paho.mqtt.client as mqtt

MB_HOST, MB_PORT, UNIT = "192.168.20.59", 5502, 7
BASE = "/sensor-cc/sensorcc"
TOPIC_REPORT = f"{BASE}/properties/report"
TOPIC_READ = f"{BASE}/properties/read"

start_ms = int(time.time() * 1000)
received = []


def on_message(_c, _u, msg):
    ts = time.time() - t0
    try:
        payload = json.loads(msg.payload.decode("utf-8", "replace"))
    except ValueError:
        payload = msg.payload[:60]
    received.append((msg.topic, payload))
    print(f"  +{ts:5.1f}s  <- {msg.topic}")
    print(f"           {str(payload)[:110]}")


t0 = time.time()
mb = ModbusTcpClient(MB_HOST, port=MB_PORT)
assert mb.connect(), "从站连接失败"
orig_h = mb.read_holding_registers(1, count=1, slave=UNIT).registers[0]

cli = mqtt.Client(client_id=f"diag5-jl-{random.randint(1000, 9999)}", clean_session=True)
cli.username_pw_set("test", "123456")
cli.on_message = on_message
cli.connect("172.16.4.211", 9783, keepalive=30)
cli.loop_start()
time.sleep(2)
print(f"开始监听 {BASE}/# (32秒) ...")

time.sleep(3)
mb.write_register(1, orig_h + 1, slave=UNIT)
print("  +5s   -> 写入reg1+1 (触发模拟器report)")

time.sleep(10)
cli.publish(TOPIC_READ, json.dumps({"messageId": "diag-006", "properties": ["temperature"]}), qos=1, retain=False)
print("  +15s  -> 发送 read 请求 (等待模拟器reply)")

time.sleep(10)
mb.write_register(1, orig_h, slave=UNIT)
print("  +25s  -> 还原reg1")

time.sleep(7)
mb.close()

got_report = any("report" in t and isinstance(p, dict) and p.get("timestamp", 0) > start_ms for t, p in received)
got_reply = any("read/reply" in t for t, _ in received)

print("\n================ 判读 ================")
print(f"1) 模拟器 report 实时到达 : {'是 -> report发布权限正常' if got_report else '否 -> report被EMQX拒绝(ACL嫌疑!)'}")
print(f"2) 模拟器 reply 实时到达  : {'是 -> reply发布权限正常' if got_reply else '否 -> reply被EMQX拒绝(ACL嫌疑!)'}")

try:
    cli.disconnect()
except Exception:
    pass
