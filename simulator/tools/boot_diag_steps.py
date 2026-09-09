# 在板子 REPL 里手动执行 boot.py v10s 的 MQTT 部分，看哪一步出错
import sys, json, time, network

print("=== STEP 1: check WiFi ===")
wlan = network.WLAN(network.STA_IF)
print("WiFi connected:", wlan.isconnected(), wlan.ifconfig()[0] if wlan.isconnected() else "N/A")

print("=== STEP 2: load umqtt ===")
from umqtt.simple import MQTTClient
print("umqtt loaded OK")

print("=== STEP 3: load config ===")
with open("/config.json") as f:
    cfg = json.load(f)
print("config:", cfg.get("product_id"), cfg.get("device_id"), cfg.get("mqtt_host"), cfg.get("mqtt_port"))

print("=== STEP 4: create + connect MQTT ===")
pid = cfg.get("product_id", "relay-cc")
did = cfg.get("device_id", "relaycc")
cid = "esp32-" + did
print("client_id:", cid)

c = MQTTClient(cid, cfg["mqtt_host"], int(cfg["mqtt_port"]),
               cfg.get("mqtt_user", ""), cfg.get("mqtt_pass", ""), keepalive=60)
print("MQTTClient created")

time.sleep_ms(500)
ret = c.connect()
print("connect ret =", ret, "(0=OK)")

print("=== STEP 5: subscribe ===")
c.set_callback(lambda t, p: print("  CALLBACK:", t, p[:80] if p else ""))
c.subscribe("relay-cc/relaycc/properties/write", qos=1)
c.subscribe("relay-cc/relaycc/properties/read", qos=1)
c.subscribe("relay-cc/relaycc/function/invoke", qos=1)
print("subscribed OK")

print("=== STEP 6: publish retain ===")
c.publish("relay-cc/relaycc/properties/report", b"", qos=0, retain=True)
print("retain published")

print("=== STEP 7: publish 5 test msgs ===")
for i in range(5):
    payload = json.dumps({"boot_diag": i, "relay1": 1, "ts": time.time()})
    c.publish("relay-cc/relaycc/properties/report", payload, qos=0)
    print("  PUB", i, payload[:60])
    time.sleep_ms(300)

print("=== STEP 8: check_msg for 10s (look for echo back) ===")
for i in range(20):
    try:
        c.check_msg()
    except Exception as e:
        print("  check_msg err:", e)
    time.sleep_ms(500)

print("=== STEP 9: keep connected, loop publish every 2s for 20s ===")
for i in range(10):
    c.publish("relay-cc/relaycc/properties/report", json.dumps({"loop_pub": i, "relay1": 1}), qos=0)
    print("  loop", i, "published")
    for j in range(4):
        try:
            c.check_msg()
        except Exception as e:
            print("  err:", e)
        time.sleep_ms(500)

print("=== ALL DONE ===")
c.disconnect()
print("disconnected")
