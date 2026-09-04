"""Day5 统一固件: 继电器设备 (MicroPython / ESP32-C3)

两种模式:
  正常运行模式 —— 用 /config.json 里的 WiFi/MQTT 配置连网,
                  按 JetLinks 协议上报 relay1~4、响应平台控制, MQTT 断线指数退避重连
  配网模式     —— SW1 长按 5 秒触发 (或首次开机无配置时自动进入);
                  设备开放热点 RELAY-SETUP-xxxx, 手机连热点后访问
                  http://192.168.4.1 填写 WiFi 与 MQTT 信息, 保存后自动重启

本地按键 (任何模式下都可用):
  SW1 短按=切继电器1  SW2(BOOT)短按=切继电器2/双击=全部  SW3=继电器3  SW4=继电器4

上传:
  mpremote cp app_config.py ap_config.py relay_hw.py main.py umqtt/simple.py :/umqtt/ ...
  mpremote reset
"""
import time
import json
import network

from umqtt.simple import MQTTClient

import relay_hw
import app_config
import ap_config


class _EnterConfig(Exception):
    """SW1 长按5秒, 请求进入配网模式"""


def log(*args):
    print("[main]", *args)


def now_ms():
    return int(time.time() * 1000)


_seq = 0


def msg_id():
    global _seq
    _seq += 1
    return "esp32-%d-%d" % (now_ms() % 100000000, _seq)


# ---------------- 正常运行模式 ----------------

_wlan = None
_cli = None
_cfg = None
T = {}


def build_topics(cfg):
    base = "/%s/%s" % (cfg["product_id"], cfg["device_id"])
    return {
        "report": base + "/properties/report",
        "write": base + "/properties/write",
        "write_reply": base + "/properties/write/reply",
        "read": base + "/properties/read",
        "read_reply": base + "/properties/read/reply",
        "invoke": base + "/function/invoke",
        "invoke_reply": base + "/function/invoke/reply",
    }


def properties():
    return {"relay%d" % (i + 1): (1 if s else 0)
            for i, s in enumerate(relay_hw.states())}


def wifi_connect(cfg, timeout_s=20):
    """连 WiFi, 成功返回 True。等待期间允许 SW1 长按进配网。"""
    global _wlan
    _wlan = network.WLAN(network.STA_IF)
    _wlan.active(True)
    if _wlan.isconnected():
        return True
    log("连接WiFi:", cfg["wifi_ssid"])
    _wlan.connect(cfg["wifi_ssid"], cfg.get("wifi_pass", ""))
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < timeout_s * 1000:
        if relay_hw.config_requested():
            raise _EnterConfig()
        if _wlan.isconnected():
            log("WiFi OK, IP:", _wlan.ifconfig()[0])
            _check_cfg()                              # 连上瞬间也可能积压长按请求
            return True
        time.sleep_ms(200)
    return _wlan.isconnected()


def _check_cfg():
    """所有阻塞/长耗时操作前后调用, 确保长按进配网不丢失"""
    if relay_hw.config_requested():
        raise _EnterConfig()


def mqtt_connect(cfg):
    global _cli
    client_id = "esp32-" + cfg["device_id"]
    _cli = MQTTClient(client_id, cfg["mqtt_host"], int(cfg["mqtt_port"]),
                      cfg.get("mqtt_user", ""), cfg.get("mqtt_pass", ""),
                      keepalive=60)
    _cli.set_callback(on_msg)
    _cli.connect()
    _cli.subscribe(T["write"], qos=1)
    _cli.subscribe(T["read"], qos=1)
    _cli.subscribe(T["invoke"], qos=1)
    _cli.publish(T["report"], b"", qos=1, retain=True)   # 清 EMQX 残留 retained
    log("MQTT 已连接 %s:%s 设备=%s" %
        (cfg["mqtt_host"], cfg["mqtt_port"], cfg["device_id"]))


def publish(topic, payload, retain=False):
    _cli.publish(topic, json.dumps(payload), qos=1, retain=retain)


def report():
    publish(T["report"], {"timestamp": now_ms(), "messageId": msg_id(),
                          "properties": properties()})
    log("上报:", properties())


def send_reply(topic, mid, extra, success=True):
    payload = {"timestamp": now_ms(), "messageId": mid, "success": success}
    payload.update(extra)
    publish(topic, payload)


def apply_props(props):
    """{"relay1":1,...} -> GPIO, 返回实际生效子集 (0/1 钳位)"""
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

    if t == T["write"]:
        applied = apply_props(cmd.get("properties", {}))
        log("属性写入 ->", applied)
        send_reply(T["write_reply"], mid, {"properties": applied}, bool(applied))
        report()
    elif t == T["read"]:
        send_reply(T["read_reply"], mid, {"properties": properties()})
        log("回复 read/reply")
    elif t == T["invoke"]:
        fid = cmd.get("functionId", "")
        params = cmd.get("inputs", cmd.get("properties", {}))
        if isinstance(params, list):       # JetLinks 数组格式转 dict
            params = {i.get("name"): i.get("value")
                      for i in params if isinstance(i, dict)}
        if fid in ("all_on", "all_off"):
            on = 1 if fid == "all_on" else 0
            for i in range(relay_hw.count()):
                relay_hw.set(i, on)
            applied = {"relay%d" % (i + 1): on
                       for i in range(relay_hw.count())}
        else:
            applied = apply_props(params)
        log("功能调用:", fid, "->", applied)
        send_reply(T["invoke_reply"], mid, {}, bool(applied))
        report()


def mqtt_loop():
    """已连接状态下的主循环, 异常向上抛触发重连。"""
    global _last_props
    _check_cfg()                                      # 进入主循环前最后检查
    report()
    _last_props = properties()
    next_check = time.ticks_add(time.ticks_ms(), 5000)
    next_ping = time.ticks_add(time.ticks_ms(), 25000)
    while True:
        if relay_hw.config_requested():
            raise _EnterConfig()
        _cli.check_msg()                              # 非阻塞处理下行命令
        now = time.ticks_ms()
        if time.ticks_diff(now, next_ping) >= 0:      # 保活
            _cli.ping()
            next_ping = time.ticks_add(now, 25000)
        if time.ticks_diff(now, next_check) >= 0:
            cur = properties()
            if cur != _last_props:                    # 本地按键/远程控制引起变化
                report()
                _last_props = cur
            next_check = time.ticks_add(now, 5000)
        time.sleep_ms(50)


def run_normal(cfg):
    """正常运行模式: WiFi/MQTT 全程自动重连 (指数退避)。"""
    global T
    T = build_topics(cfg)
    backoff = 5
    while True:
        try:
            wifi_connect(cfg)                        # 内部已含 _check_cfg
            _check_cfg()                              # WiFi 刚连上 → MQTT 间隙
            mqtt_connect(cfg)
            _check_cfg()                              # MQTT 刚连上 → mqtt_loop 间隙
            backoff = 5                                # 连上后重置退避
            mqtt_loop()
        except _EnterConfig:
            raise
        except Exception as e:
            log("连接异常:", e, "-> %ds 后重连" % backoff)
            try:
                if _cli:
                    _cli.disconnect()
            except Exception:
                pass
            t0 = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), t0) < backoff * 1000:
                if relay_hw.config_requested():
                    raise _EnterConfig()
                time.sleep_ms(200)
            backoff = min(backoff * 2, 60)             # 5->10->20->40->60s 封顶


# ---------------- 启动 ----------------

def main():
    relay_hw.init()
    relay_hw.attach_buttons()
    log("设备启动, MAC =", app_config.mac_address())

    cfg = app_config.load()
    if not app_config.is_ready(cfg):
        log("未检测到有效配置, 进入配网模式")
        ap_config.run(cfg)                            # 阻塞, 保存后自动重启
        return

    while True:
        try:
            run_normal(cfg)
        except _EnterConfig:
            log("收到配网请求, 切换到配网模式")
            try:
                if _cli:
                    _cli.disconnect()
            except Exception:
                pass
            ap_config.run(app_config.load() or cfg)   # 阻塞, 保存后自动重启


main()
