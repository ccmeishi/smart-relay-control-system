"""诊断组合版: 同时验证模拟器的发布链路和订阅链路

流程:
  1. 订阅 /sensor-cc/sensorcc/# (只认新消息)
  2. 写从站 reg1+1 触发模拟器实时上报  -> 验证"发布链路" (MQTT 出)
  3. 发送标准 read 请求                -> 验证"订阅链路" (MQTT 入)
  4. 还原寄存器
判读:
  - 有新上报 + 有 reply  -> 设备侧全通, 问题在平台
  - 有新上报 + 无 reply  -> 模拟器"能发不能收" -> 订阅被ACL拒绝或session异常
  - 无新上报             -> 模拟器 MQTT 又死了 (client_id 冲突互踢?)
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
TOPIC_REPLY = f"{BASE}/properties/read/reply"

start_ms = int(time.time() * 1000)
events = {"report": None, "reply": None}


def on_message(_c, _u, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8", "replace"))
    except ValueError:
        return
    if "report" in msg.topic and payload.get("timestamp", 0) > start_ms:
        events["report"] = payload
        print(f"[新上报] {payload.get('properties')}")
    elif "read/reply" in msg.topic:
        events["reply"] = payload
        print(f"[read回复] {json.dumps(payload, ensure_ascii=False)[:100]}")


mb = ModbusTcpClient(MB_HOST, port=MB_PORT)
assert mb.connect(), "从站连接失败"
orig_h = mb.read_holding_registers(1, count=1, slave=UNIT).registers[0]
print(f"[从站] reg1湿度={orig_h}")

cli = mqtt.Client(client_id=f"diag4-jl-{random.randint(1000, 9999)}", clean_session=True)
cli.username_pw_set("test", "123456")
cli.on_message = on_message
cli.connect("172.16.4.211", 9783, keepalive=30)
cli.loop_start()
time.sleep(2)

# --- 测试1: 发布链路 ---
mb.write_register(1, orig_h + 1, slave=UNIT)
print("[触发] reg1+1, 等待模拟器上报 (8秒)...")
deadline = time.time() + 8
while time.time() < deadline and not events["report"]:
    time.sleep(0.2)

# --- 测试2: 订阅链路 ---
cli.publish(TOPIC_READ, json.dumps({"messageId": "diag-005", "properties": ["temperature"]}), qos=1, retain=False)
print("[发送] read 请求, 等待模拟器回复 (5秒)...")
deadline = time.time() + 5
while time.time() < deadline and not events["reply"]:
    time.sleep(0.2)

mb.write_register(1, orig_h, slave=UNIT)
mb.close()
print("[还原] reg1")

print("\n================ 判读 ================")
if events["report"] and events["reply"]:
    print("发布链路 OK + 订阅链路 OK -> 设备侧完全正常, 问题确定在平台!")
elif events["report"] and not events["reply"]:
    print("发布链路 OK 但收不到回复 -> 模拟器'能发不能收' -> 订阅被ACL拒绝/订阅丢失!")
    print("  -> 去EMQX Dashboard -> 访问控制 -> 客户端认证/授权, 查 test 用户的订阅权限")
elif not events["report"]:
    print("连实时上报都没有 -> 模拟器 MQTT 又死了 -> 检查是否有第二个同 client_id 实例在互踢!")

try:
    cli.disconnect()
except Exception:
    pass
