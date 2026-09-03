"""诊断终极版: 主动改从站湿度寄存器触发模拟器实时上报, 验证模拟器 MQTT 存活

流程:
  1. 读从站 reg0/reg1 原值
  2. 订阅 report topic (只认 timestamp > 测试开始 的消息, 排除 retained 残留)
  3. 写 reg1 = 原值+1  -> 模拟器 5 秒轮询应发现变化并上报
  4. 等 15 秒收新 report, 然后把 reg1 写回原值
判读:
  - 收到新 report -> 模拟器 MQTT 连接和发布完全正常, 问题聚焦在"订阅丢失"
  - 没收到        -> 模拟器的 MQTT 是半开假在线, 必须重启模拟器
"""

import json
import time
import random

from pymodbus.client import ModbusTcpClient
import paho.mqtt.client as mqtt

MB_HOST, MB_PORT, UNIT = "192.168.20.59", 5502, 7
TOPIC_REPORT = "/sensor-cc/sensorcc/properties/report"

start_ms = int(time.time() * 1000)
new_reports = []


def on_message(_c, _u, msg):
    try:
        payload = json.loads(msg.payload.decode("utf-8", "replace"))
    except ValueError:
        return
    ts = payload.get("timestamp", 0)
    if ts > start_ms:   # 排除 retained 残留
        new_reports.append(payload)
        print(f"[新上报] ts={ts}  {payload.get('properties')}")


# ---- 1. 读从站原值 ----
mb = ModbusTcpClient(MB_HOST, port=MB_PORT)
assert mb.connect(), "从站连接失败"
rr = mb.read_holding_registers(0, count=2, slave=UNIT)
orig_t, orig_h = rr.registers[0], rr.registers[1]
print(f"[从站] reg0温度={orig_t}({orig_t/10}C)  reg1湿度={orig_h}({orig_h/10}%)")

# ---- 2. 订阅 report ----
cli = mqtt.Client(client_id=f"diag3-jl-{random.randint(1000, 9999)}", clean_session=True)
cli.username_pw_set("test", "123456")
cli.on_message = on_message
cli.connect("172.16.4.211", 9783, keepalive=30)
cli.loop_start()
time.sleep(2)

# ---- 3. 写 reg1+1 触发变化 ----
mb.write_register(1, orig_h + 1, slave=UNIT)
print(f"[写入] reg1: {orig_h} -> {orig_h+1}  (等待模拟器轮询上报, 最多15秒)")

deadline = time.time() + 15
while time.time() < deadline and not new_reports:
    time.sleep(0.2)

# ---- 4. 还原 ----
mb.write_register(1, orig_h, slave=UNIT)
print(f"[还原] reg1: -> {orig_h}")
mb.close()

print("\n================ 判读 ================")
if new_reports:
    print(f"模拟器 MQTT 完全正常! 收到 {len(new_reports)} 条实时上报 -> 问题聚焦: 订阅丢失/下行不通")
else:
    print("15秒无实时上报 -> 模拟器 MQTT 是'半开假在线', 直接重启模拟器窗口即可")

try:
    cli.disconnect()
except Exception:
    pass
