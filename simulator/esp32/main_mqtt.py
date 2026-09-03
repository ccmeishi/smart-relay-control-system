"""路线A: ESP32 直连 EMQX -> JetLinks (MicroPython)

板子本身就是完整设备: 继电器接在自家 GPIO 上, 无需 Modbus、无需 PC 开机。
  上报  /relay-cc/relaycc/properties/report      (仅 relay1~4, 0/1 钳位)
  响应  properties/write | properties/read | function/invoke (all_on/all_off/单路)
平台配置零改动, 直接沿用继电器-cc 产品。

注意:
  1. client_id = relaycc-esp32, 与 PC 模拟器不同, 不会互踢
  2. 实物测试时必须关掉 PC 的 relay_simulator_jl.py, 同一设备双上报会让平台会话错乱

上传到板子:
  mpremote cp config.py relay_hw.py main_mqtt.py :/
  mpremote fs mkdir :/umqtt  (首次)
  mpremote cp umqtt/simple.py :/umqtt/simple.py
  mpremote cp main_mqtt.py :/main.py     # 设为开机自启
  mpremote reset                         # 重启生效
"""
import json
import time
import network
import ntptime
from umqtt.simple import MQTTClient

import config as C
import relay_hw

_T = "/%s/%s/properties" % (C.PRODUCT_ID, C.DEVICE_ID)
TOPIC_REPORT = _T + "/report"
TOPIC_WRITE = _T + "/write"
TOPIC_WRITE_REPLY = _T + "/write/reply"
TOPIC_READ = _T + "/read"
TOPIC_READ_REPLY = _T + "/read/reply"
TOPIC_INVOKE = "/%s/%s/function/invoke" % (C.PRODUCT_ID, C.DEVICE_ID)
TOPIC_INVOKE_REPLY = "/%s/%s/function/invoke/reply" % (C.PRODUCT_ID, C.DEVICE_ID)

_wlan = None
_cli = None
_last_report = None
_seq = 0


def log(*args):
    print("[mqtt]", *args)


def now_ms():
    return int(time.time() * 1000)


def msg_id():
    global _seq
    _seq += 1
    return "esp32-%d-%d" % (now_ms() % 100000000, _seq)


def properties():
    """平台属性: relay1~4, 强制 0/1"""
    props = {}
    for i, s in enumerate(relay_hw.states()):
        props["relay%d" % (i + 1)] = 1 if s else 0
    return props


def ensure_wifi():
    global _wlan
    _wlan = network.WLAN(network.STA_IF)
    if not _wlan.isconnected():
        _wlan.active(True)
        log("连接WiFi:", C.WIFI_SSID)
        _wlan.connect(C.WIFI_SSID, C.WIFI_PASS)
        for _ in range(200):
            time.sleep_ms(200)
            if _wlan.isconnected():
                break
    if not _wlan.isconnected():
        raise OSError("WiFi 连接失败")
    log("WiFi OK, IP:", _wlan.ifconfig()[0])
    try:
        ntptime.settime()               # 同步 UTC 时间, 保证毫秒时间戳正确
    except Exception as e:
        log("NTP 同步失败(不影响功能):", e)


def mqtt_connect():
    global _cli
    _cli = MQTTClient(C.MQTT_CLIENT_ID, C.MQTT_HOST, C.MQTT_PORT,
                      C.MQTT_USER, C.MQTT_PASS, keepalive=0)
    _cli.set_callback(on_msg)
    _cli.connect()
    _cli.subscribe(TOPIC_WRITE, qos=1)
    _cli.subscribe(TOPIC_READ, qos=1)
    _cli.subscribe(TOPIC_INVOKE, qos=1)
    # 清除 EMQX 残留 retained 消息 (与 PC 模拟器行为一致)
    _cli.publish(TOPIC_REPORT, b"", qos=1, retain=True)
    log("MQTT 已连接 %s:%s" % (C.MQTT_HOST, C.MQTT_PORT))


def publish(topic, payload, retain=False):
    _cli.publish(topic, json.dumps(payload), qos=1, retain=retain)


def report():
    publish(TOPIC_REPORT, {"timestamp": now_ms(), "messageId": msg_id(),
                           "properties": properties()})
    log("上报:", properties())


def send_reply(topic, mid, extra, success=True):
    payload = {"timestamp": now_ms(), "messageId": mid, "success": success}
    payload.update(extra)
    publish(topic, payload)


def apply_props(props):
    """把 {"relay1":1,...} 写到 GPIO, 返回实际生效的子集 (值已钳位 0/1)"""
    applied = {}
    for k, v in props.items():
        if not k.startswith("relay"):
            continue
        try:
            idx = int(k[5:]) - 1
        except ValueError:
            continue
        if 0 <= idx < relay_hw.count():
            on = 1 if int(v) else 0
            relay_hw.set(idx, on)
            applied[k] = on
    return applied


def on_msg(topic, payload):
    t = topic.decode() if isinstance(topic, bytes) else topic
    try:
        cmd = json.loads(payload)
    except ValueError:
        log("非JSON消息:", payload[:60])
        return
    mid = cmd.get("messageId", msg_id())

    if t == TOPIC_WRITE:
        props = cmd.get("properties", {})
        applied = apply_props(props)
        log("属性写入:", props, "->", applied)
        send_reply(TOPIC_WRITE_REPLY, mid, {"properties": applied}, bool(applied))
        report()

    elif t == TOPIC_READ:
        send_reply(TOPIC_READ_REPLY, mid, {"properties": properties()})
        log("回复 read/reply")

    elif t == TOPIC_INVOKE:
        fid = cmd.get("functionId", "")
        params = cmd.get("inputs", cmd.get("properties", {}))
        if isinstance(params, list):        # JetLinks 数组格式转 dict
            params = {i.get("name"): i.get("value")
                      for i in params if isinstance(i, dict)}
        if fid in ("all_on", "all_off"):
            on = 1 if fid == "all_on" else 0
            for i in range(relay_hw.count()):
                relay_hw.set(i, on)
            applied = {"relay%d" % (i + 1): on for i in range(relay_hw.count())}
        else:
            applied = apply_props(params)
        log("功能调用:", fid, params, "->", applied)
        send_reply(TOPIC_INVOKE_REPLY, mid, {}, bool(applied))
        report()


def run():
    ensure_wifi()
    relay_hw.init()
    global _last_report
    while True:
        try:
            mqtt_connect()
            report()
            _last_report = properties()
            next_check = time.ticks_add(time.ticks_ms(), 5000)
            while True:
                _cli.check_msg()                       # 处理下行命令
                if time.ticks_diff(time.ticks_ms(), next_check) >= 0:
                    cur = properties()
                    if cur != _last_report:            # 值变化才上报, 省流量
                        report()
                        _last_report = cur
                    next_check = time.ticks_add(time.ticks_ms(), 5000)
                time.sleep_ms(50)
        except Exception as e:
            log("连接异常, 5s后重连:", e)
            try:
                _cli.disconnect()
            except Exception:
                pass
            time.sleep(5)
            try:
                ensure_wifi()
            except Exception as e2:
                log("WiFi 重连失败:", e2)


run()
