"""boot.py - v12 最终版: boot.py 预连 WiFi + MQTT, 然后 exec main.py
exec 共享全局命名空间, main.py 可直接使用 _cli / _TOPICS
"""
import time, json, network, os, sys

print("BOOT v12 start")

# ---------- 1. config.json ----------
try:
    os.stat("/config.json")
    print("  cfg exists")
except OSError:
    CONFIG = {
        "wifi_ssid": "Office-WiFi", "wifi_pass": "yh82922868",
        "mqtt_host": "172.16.4.211", "mqtt_port": 9783,
        "mqtt_user": "test", "mqtt_pass": "123456",
        "product_id": "relay-cc", "device_id": "relaycc",
        "modbus_slaves": [{
            "name": "第七组模拟器",
            "host": "192.168.20.59", "port": 5502, "unit_id": 7,
            "points": [
                {"addr": "0x0000", "key": "temperature", "period_ms": 3000, "count": 1, "type": "uint16", "scale": 0.1},
                {"addr": "0x0001", "key": "humidity",    "period_ms": 5000, "count": 1, "type": "uint16", "scale": 0.1},
                {"addr": "0x0002", "key": "current",     "period_ms": 10000, "count": 1, "type": "uint16", "scale": 0.1},
                {"addr": "0x0003", "key": "voltage",     "period_ms": 10000, "count": 1, "type": "uint16", "scale": 0.1},
                {"addr": "0x0004", "key": "human",       "period_ms": 3000, "count": 1, "type": "uint16", "scale": 1},
                {"addr": "0x0005", "key": "smoke",       "period_ms": 3000, "count": 1, "type": "uint16", "scale": 1},
            ]
        }]
    }
    with open("/config.json", "w") as f:
        json.dump(CONFIG, f)
    print("  cfg created")

# ---------- 2. WiFi ----------
print("  connecting WiFi...")
wlan = network.WLAN(network.STA_IF)
wlan.active(True)
wlan.connect("Office-WiFi", "yh82922868")
for i in range(30):
    time.sleep_ms(500)
    if wlan.isconnected():
        print("  WiFi OK IP=", wlan.ifconfig()[0])
        break
else:
    print("  WiFi FAIL, stop")
    while True:
        time.sleep(1)

# ---------- 3. MQTT (boot.py 预连, main.py 直接用) ----------
print("  loading config...")
with open("/config.json") as f:
    _cfg = json.load(f)

_pid = _cfg.get("product_id", "relay-cc")
_did = _cfg.get("device_id", "relaycc")
_cid = "esp32-" + _did

print("  connecting MQTT %s:%s as %s ..." % (_cfg["mqtt_host"], _cfg["mqtt_port"], _cid))
from umqtt.simple import MQTTClient
_cli = MQTTClient(_cid, _cfg["mqtt_host"], int(_cfg["mqtt_port"]),
                  _cfg.get("mqtt_user", ""), _cfg.get("mqtt_pass", ""), keepalive=60)
time.sleep_ms(300)
ret = _cli.connect()
print("  MQTT ret=", ret)

# 构建 topics (main.py 会用)
_base = "%s/%s" % (_pid, _did)
_TOPICS = {
    "report": _base + "/properties/report",
    "event": _base + "/event",
    "write": _base + "/properties/write",
    "write_reply": _base + "/properties/write/reply",
    "read": _base + "/properties/read",
    "read_reply": _base + "/properties/read/reply",
    "invoke": _base + "/function/invoke",
    "invoke_reply": _base + "/function/invoke/reply",
}

# subscribe 前必须设 callback (qos=1 subscribe 会 wait_msg, 可能收到 retain 回发)
def _boot_cb(t, p):
    pass  # 临时 callback, main.py exec 后会替换为 on_msg

_cli.set_callback(_boot_cb)
_cli.subscribe(_TOPICS["write"], qos=1)
_cli.subscribe(_TOPICS["read"], qos=1)
_cli.subscribe(_TOPICS["invoke"], qos=1)

# 在线标记
_cli.publish(_TOPICS["report"], b"", qos=0, retain=True)

# 标记: boot.py 已经连好 MQTT, main.py 跳过 connect
_BOOT_GAVE_CLIENT = True
print("  MQTT READY, product=%s device=%s" % (_pid, _did))

# ---------- 4. exec main.py (共享全局命名空间) ----------
print("BOOT v12 exec main.py ...")
time.sleep_ms(200)
try:
    exec(open("/main.py").read())
    # exec 后 main() 函数已定义, 手动调用
    print("BOOT v12 calling main() ...")
    main()
except Exception as e:
    print("main.py crashed:", e)
    sys.print_exception(e)
