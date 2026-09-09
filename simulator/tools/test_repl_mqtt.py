# 板子 REPL 里跑这个脚本验证 MQTT
import sys
from umqtt.simple import MQTTClient

print("=== MQTT MANUAL TEST ===")
c = MQTTClient("esp32-repl-test", "172.16.4.211", 9783, "test", "123456", keepalive=30)
print("1. connecting...")
ret = c.connect()
print("   ret =", ret, "(0=OK)")

print("2. publish 3 msgs...")
for i in range(3):
    payload = '{"test":"repl-manual-' + str(i) + '","relay1":1}'
    c.publish("relay-cc/relaycc/properties/report", payload, qos=0)
    print("   PUB", i, payload)

print("3. subscribe self + check_msg...")
c.set_callback(lambda t, p: print("   RECV:", t, p[:60]))
c.subscribe("relay-cc/relaycc/#")

import time
for i in range(10):
    try:
        c.check_msg()
    except Exception as e:
        print("   check_msg err:", e)
    time.sleep_ms(500)

print("=== DONE ===")
c.disconnect()
