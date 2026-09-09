"""Day9 网关固件: 单 ESP32 → 统一上报 → Python Bridge 分发到多个虚拟设备

架构 (vs Day8 多 client 直连):
  Day8 (已废弃): ESP32 开 2 个 MQTTClient 分别连 relay-cc 和 sensor-cc
  Day9 (现在):  ESP32 开 1 个 MQTTClient, 所有数据汇总上报到网关产品,
                Python Bridge 服务订阅网关 topic 后按 routing table 拆分转发

网关上报 payload 包含所有 key:
  relay1..relay4 (GPIO 真源)
  temperature, humidity (Modbus 采集)
  human, smoke (Modbus 模拟多寄存器)

ESP32 只连 1 个网关产品, 建议创建专门的 esp32-gateway 产品,
把所有属性都定义在它的物模型里 (relay1~4, temperature, humidity, human, smoke)。
"""
import time
import json
import network
import ntptime
import machine

from umqtt.simple import MQTTClient

import relay_hw
import app_config
import ap_config
import modbus_gw


class _EnterConfig(Exception):
    """SW1 长按5秒, 请求进入配网模式"""


def log(*args):
    print("[main]", *args)


# ---------- NTP ----------

_NTP_OFFSET = 0


def _compute_epoch(dt):
    Y, M, D, H, Mi, S = dt[:6]
    total_days = (Y - 1970) * 365
    leaps = sum(1 for y in range(1970, Y) if (y % 4 == 0 and y % 100 != 0) or y % 400 == 0)
    total_days += leaps
    days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    if (Y % 4 == 0 and Y % 100 != 0) or Y % 400 == 0:
        days_in_month[1] = 29
    total_days += sum(days_in_month[:M - 1]) + (D - 1)
    return total_days * 86400 + H * 3600 + Mi * 60 + S


def now_ms():
    return int((time.time() + _NTP_OFFSET) * 1000)


_seq = 0


def msg_id():
    global _seq
    _seq += 1
    return "esp32-%d-%d" % (now_ms() % 100000000, _seq)


# ---------------- 全局 ----------------
# boot.py v12 可能已预连 MQTT 并设了 _cli / _TOPICS / _BOOT_GAVE_CLIENT
# exec 共享命名空间, 这里用 globals().get() 避免覆盖

_wlan = None
_cli = globals().get('_cli')           # boot.py 预连的 MQTTClient
_TOPICS = globals().get('_TOPICS', {})  # boot.py 构建的 topics dict
_last_props = None
_BOOT_GAVE_CLIENT = globals().get('_BOOT_GAVE_CLIENT', False)


def accept_boot_mqtt(c, topics):
    """boot.py 预连好 MQTT 后调这个, 跳过 mqtt_connect 里的 connect/subscribe"""
    global _cli, _TOPICS, _BOOT_GAVE_CLIENT
    _cli = c
    _TOPICS = topics
    _BOOT_GAVE_CLIENT = True
    c.set_callback(on_msg)
    log("已接收 boot.py 预连好的 MQTTClient")


def build_topics(product_id, device_id):
    base = "%s/%s" % (product_id, device_id)
    return {
        "report": base + "/properties/report",
        "event": base + "/event",
        "write": base + "/properties/write",
        "write_reply": base + "/properties/write/reply",
        "read": base + "/properties/read",
        "read_reply": base + "/properties/read/reply",
        "invoke": base + "/function/invoke",
        "invoke_reply": base + "/function/invoke/reply",
    }


def properties():
    """返回所有数据 (GPIO + Modbus), Bridge 会按 key 路由"""
    p = {"relay%d" % (i + 1): (1 if s else 0)
         for i, s in enumerate(relay_hw.states())}
    mb = modbus_gw.collected()
    if mb:
        p.update(mb)
    return p


# ---------------- WiFi + NTP ----------------

def wifi_connect(cfg, timeout_s=20):
    global _wlan
    _wlan = network.WLAN(network.STA_IF)
    _wlan.active(True)
    if _wlan.isconnected():
        log("WiFi already connected, IP:", _wlan.ifconfig()[0])
        _ntp_sync()
        return True
    log("连接WiFi:", cfg["wifi_ssid"])
    _wlan.connect(cfg["wifi_ssid"], cfg.get("wifi_pass", ""))
    t0 = time.ticks_ms()
    while time.ticks_diff(time.ticks_ms(), t0) < timeout_s * 1000:
        if relay_hw.config_requested():
            raise _EnterConfig()
        if _wlan.isconnected():
            log("WiFi OK, IP:", _wlan.ifconfig()[0])
            _check_cfg()
            _ntp_sync()
            return True
        time.sleep_ms(200)
    return _wlan.isconnected()


def _ntp_sync():
    global _NTP_OFFSET
    try:
        ntptime.host = "ntp.aliyun.com"
        ntptime.settime()
        rtc_dt = machine.RTC().datetime()
        _NTP_OFFSET = _compute_epoch(rtc_dt) - int(time.time())
        log("[TIME] offset:", _NTP_OFFSET)
    except Exception as e:
        log("[TIME] NTP FAILED:", repr(e))
        try:
            ntptime.host = "pool.ntp.org"
            ntptime.settime()
            rtc_dt = machine.RTC().datetime()
            _NTP_OFFSET = _compute_epoch(rtc_dt) - int(time.time())
        except Exception as e2:
            log("[TIME] fallback also FAILED:", repr(e2))


def _check_cfg():
    if relay_hw.config_requested():
        raise _EnterConfig()


# ---------------- MQTT ----------------

def _resolve_gateway(cfg):
    """从 Day9 config 或 Day8 devices[] 中取出网关设备的 product_id/device_id"""
    # Day9: 顶层有 product_id + device_id
    pid = cfg.get("product_id")
    did = cfg.get("device_id")
    if pid and did:
        return pid, did
    # Day8: devices[0] 就是网关
    devs = cfg.get("devices", [])
    if devs:
        return devs[0].get("product_id", ""), devs[0].get("device_id", "")
    return "relay-cc", "relaycc"


def mqtt_connect(cfg):
    global _cli, _TOPICS, _BOOT_GAVE_CLIENT
    pid, did = _resolve_gateway(cfg)
    if _BOOT_GAVE_CLIENT and _cli is not None:
        # boot.py 已经连好 MQTT 了, 跳过 connect/subscribe
        _cli.set_callback(on_msg)
        log("MQTT 已存在 (boot.py 预连) 网关产品=%s 设备=%s" % (pid, did))
        return
    # 自己连 MQTT
    client_id = "esp32-" + did
    _cli = MQTTClient(client_id, cfg["mqtt_host"], int(cfg["mqtt_port"]),
                      cfg.get("mqtt_user", ""), cfg.get("mqtt_pass", ""),
                      keepalive=60)
    _cli.set_callback(on_msg)
    _cli.connect()
    _TOPICS = build_topics(pid, did)
    _cli.subscribe(_TOPICS["write"], qos=1)
    _cli.subscribe(_TOPICS["read"], qos=1)
    _cli.subscribe(_TOPICS["invoke"], qos=1)
    _cli.publish(_TOPICS["report"], b"", qos=0, retain=True)
    log("MQTT 已连接 %s:%s 网关产品=%s 设备=%s" % (cfg["mqtt_host"], cfg["mqtt_port"], pid, did))


def report():
    _cli.publish(_TOPICS["report"], json.dumps({
        "timestamp": now_ms(), "messageId": msg_id(), "properties": properties()
    }), qos=0)


def send_reply(topic, mid, extra, success=True):
    payload = {"timestamp": now_ms(), "messageId": mid, "success": success}
    payload.update(extra)
    _cli.publish(topic, json.dumps(payload), qos=0)


def publish_event(event_id, data):
    """网关级别 Event 事件 (JetLinks 日志管理)"""
    _cli.publish(_TOPICS["event"] + "/" + event_id, json.dumps({
        "timestamp": now_ms(), "messageId": msg_id(), "data": data
    }), qos=0)


def relay_writeback_modbus():
    """继电器状态变化时, 写回 Modbus 共享模拟器 0x0006~0x0009
    第七组 unit_id=7, 0x0006=relay1, 0x0007=relay2, 0x0008=relay3, 0x0009=relay4
    """
    mb_slaves = app_config.load().get("modbus_slaves", [])
    if not mb_slaves:
        return
    unit_id = mb_slaves[0].get("unit_id", 1)
    for i, state in enumerate(relay_hw.states()):
        addr = 0x0006 + i
        val = 1 if state else 0
        try:
            ok = modbus_gw.write_holding(unit_id, addr, val)
            log("[modbus] relay_writeback unit_id=%d addr=0x%04X val=%d ok=%s"
                % (unit_id, addr, val, ok))
        except Exception as e:
            log("[modbus] relay_writeback failed:", e)


def apply_props(props):
    """写属性: 只有 relay* 开头的 key 能作用到 GPIO"""
    applied = {}
    for k, v in props.items():
        if k.startswith("relay"):
            try:
                idx = int(k[5:]) - 1
            except ValueError:
                continue
            if 0 <= idx < relay_hw.count():
                on = 1 if int(v) else 0
                relay_hw.set(idx, on)
                applied[k] = on
    if applied:
        relay_writeback_modbus()
    return applied


def on_msg(topic, payload):
    t = topic.decode() if isinstance(topic, bytes) else topic
    try:
        cmd = json.loads(payload)
    except ValueError:
        log("非JSON消息:", payload[:60])
        return
    mid = cmd.get("messageId", msg_id())

    if t == _TOPICS["write"]:
        props_in = cmd.get("properties", {})
        applied = apply_props(props_in)
        log("属性写入 ->", applied)
        send_reply(_TOPICS["write_reply"], mid, {"properties": applied}, bool(applied))
        report()
        if applied:
            publish_event("relay_changed", applied)
    elif t == _TOPICS["read"]:
        send_reply(_TOPICS["read_reply"], mid, {"properties": properties()})
    elif t == _TOPICS["invoke"]:
        fid = cmd.get("functionId", "")
        params = cmd.get("inputs", cmd.get("properties", {}))
        if isinstance(params, list):
            params = {i.get("name"): i.get("value")
                      for i in params if isinstance(i, dict)}
        if fid in ("all_on", "all_off"):
            on = 1 if fid == "all_on" else 0
            for i in range(relay_hw.count()):
                relay_hw.set(i, on)
            applied = {"relay%d" % (i + 1): on for i in range(relay_hw.count())}
        elif fid == "set_relay":
            idx = int(params.get("继电器编号", params.get("relay", 0))) - 1
            on = 1 if int(params.get("状态", params.get("state", 0))) else 0
            if 0 <= idx < relay_hw.count():
                relay_hw.set(idx, on)
                applied = {"relay%d" % (idx + 1): on}
            else:
                applied = {}
        elif fid == "toggle_relay":
            idx = int(params.get("继电器编号", params.get("relay", 0))) - 1
            if 0 <= idx < relay_hw.count():
                relay_hw.toggle(idx) if hasattr(relay_hw, 'toggle') else None
                applied = {"relay%d" % (idx + 1): relay_hw.get(idx)}
            else:
                applied = {}
        elif fid == "batch_set":
            applied = {}
            for k, v in params.items():
                if k.startswith("relay"):
                    try:
                        i = int(k[5:]) - 1
                        if 0 <= i < relay_hw.count():
                            relay_hw.set(i, 1 if int(v) else 0)
                            applied[k] = 1 if int(v) else 0
                    except ValueError:
                        pass
        else:
            applied = apply_props(params)
        log("功能调用:", fid, params, "->", applied)
        send_reply(_TOPICS["invoke_reply"], mid, {}, bool(applied))
        report()
        if applied:
            relay_writeback_modbus()
            publish_event("relay_changed", applied)


# ---------------- 主循环 ----------------

def mqtt_loop():
    global _last_props
    _check_cfg()
    report()
    publish_event("device_start", {"uptime_s": 0})
    _last_props = properties()
    next_check = time.ticks_add(time.ticks_ms(), 5000)
    next_ping = time.ticks_add(time.ticks_ms(), 25000)

    while True:
        if relay_hw.config_requested():
            raise _EnterConfig()

        try:
            _cli.check_msg()
        except OSError as e:
            log("check_msg 异常:", e)
            raise

        modbus_gw.poll_one()
        now = time.ticks_ms()

        if time.ticks_diff(now, next_ping) >= 0:
            try:
                _cli.ping()
            except Exception:
                raise
            next_ping = time.ticks_add(now, 25000)

        if time.ticks_diff(now, next_check) >= 0:
            cur = properties()
            if cur != _last_props:
                report()
                publish_event("data_changed", {k: v for k, v in cur.items() if _last_props.get(k) != v})
                _last_props = cur
            next_check = time.ticks_add(now, 5000)

        time.sleep_ms(50)


# ---------------- 正常运行 ----------------

def run_normal(cfg):
    global _cli
    backoff = 5
    while True:
        try:
            wifi_connect(cfg)
            _check_cfg()
            mqtt_connect(cfg)
            _check_cfg()

            mb_slaves = cfg.get("modbus_slaves", [])
            if mb_slaves:
                modbus_gw.init(mb_slaves)
                log("Modbus 网关已启动, 采集点:", modbus_gw.point_count())
            else:
                modbus_gw.close()

            backoff = 5
            mqtt_loop()
        except _EnterConfig:
            raise
        except Exception as e:
            log("循环异常:", e, "-> %ds 后重连" % backoff)
            try:
                if _cli:
                    _cli.disconnect()
            except Exception:
                pass
            _cli = None
            modbus_gw.close()

            t0 = time.ticks_ms()
            while time.ticks_diff(time.ticks_ms(), t0) < backoff * 1000:
                if relay_hw.config_requested():
                    raise _EnterConfig()
                time.sleep_ms(200)
            backoff = min(backoff * 2, 60)


# ---------------- 启动 ----------------

def main():
    relay_hw.init()
    relay_hw.attach_buttons()
    log("设备启动, MAC =", app_config.mac_address())

    cfg = app_config.load()
    if not app_config.is_ready(cfg):
        log("未检测到有效配置, 进入配网模式")
        ap_config.run(cfg)
        return

    while True:
        try:
            run_normal(cfg)
        except _EnterConfig:
            log("收到配网请求, 重启进入配网模式")
            # 运行中直接切 STA->AP 会被 MQTT/Modbus 残留 socket 挂死;
            # 写标记后重启, 由 boot.py 在干净状态进入配网
            try:
                with open("/force_ap", "w") as _f:
                    _f.write("1")
            except Exception:
                pass
            time.sleep_ms(300)
            machine.reset()


if __name__ == "__main__":
    main()
