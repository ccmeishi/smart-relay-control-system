"""用户配置持久化 (Day9 网关版)

配置保存在板子 Flash 的 /config.json, 断电不丢;
首次使用或 SW1 长按 5 秒进入配网模式时, 由 ap_config.py 网页写入。

Day9 架构 (当前):
  单网关模式: ESP32 连 1 个网关产品, 所有数据汇总上报,
  Python Bridge 服务订阅网关 topic 后按 routing table 拆分转发到多虚拟产品。

  config.json 为 flat 结构:
  {
    "wifi_ssid": "...", "wifi_pass": "...",
    "mqtt_host": "...", "mqtt_port": 9783,
    "mqtt_user": "...", "mqtt_pass": "...",
    "product_id": "relay-cc",  ← 网关产品
    "device_id": "relaycc",    ← 网关设备
    "modbus_slaves": [...]
  }

Day8 devices[] 格式自动迁移.
"""
import json
import ubinascii
import network

CONFIG_PATH = "/config.json"

# 出厂默认值 (网页表单预填; 设备ID 默认取 MAC 地址)
DEFAULTS = {
    "wifi_ssid": "",
    "wifi_pass": "",
    "mqtt_host": "172.16.4.211",
    "mqtt_port": 9783,
    "mqtt_user": "test",
    "mqtt_pass": "123456",
    # Day9: flat 结构, 单网关产品
    "product_id": "relay-cc",
    "device_id": "",   # 空 → 首次加载时自动填 MAC 后 8 位
    # Modbus 采集网关: 第七小组专用
    # 共享模拟器 192.168.20.59:5502, 组号 = unit_id = 7
    # 寄存器范围 0x0000 ~ 0x0009, 避免跟其他小组冲突
    "modbus_slaves": [
        {
            "name": "第七组-多寄存器模拟器",
            "host": "192.168.20.59",
            "port": 5502,
            "unit_id": 7,
            "points": [
                {"addr": "0x0000", "key": "temperature", "period_ms": 3000,
                 "count": 1, "type": "uint16", "scale": 0.1},
                {"addr": "0x0001", "key": "humidity",    "period_ms": 5000,
                 "count": 1, "type": "uint16", "scale": 0.1},
                {"addr": "0x0002", "key": "current",     "period_ms": 10000,
                 "count": 1, "type": "uint16", "scale": 0.1},
                {"addr": "0x0003", "key": "voltage",     "period_ms": 10000,
                 "count": 1, "type": "uint16", "scale": 0.1},
                {"addr": "0x0004", "key": "human",       "period_ms": 3000,
                 "count": 1, "type": "uint16", "scale": 1},
                {"addr": "0x0005", "key": "smoke",       "period_ms": 3000,
                 "count": 1, "type": "uint16", "scale": 1},
            ],
        },
    ],
}

# 正常运行必须有的字段 (缺任何一个都视为未配网)
REQUIRED = ("wifi_ssid", "mqtt_host")


def mac_address():
    """返回 12 位小写 MAC 十六进制, 如 'a4cf12c8b190'"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    return ubinascii.hexlify(wlan.config("mac")).decode()


def defaults():
    d = json.loads(json.dumps(DEFAULTS))   # 深拷贝
    d["device_id"] = mac_address()[-8:]
    return d


def _migrate_day8(cfg):
    """Day8 devices[] → Day9 flat 格式"""
    if "product_id" in cfg and "device_id" in cfg:
        return cfg   # 已经是 flat, 不需要迁

    mac = mac_address()
    new_cfg = {
        "wifi_ssid": cfg.get("wifi_ssid", ""),
        "wifi_pass": cfg.get("wifi_pass", ""),
        "mqtt_host": cfg.get("mqtt_host", "172.16.4.211"),
        "mqtt_port": cfg.get("mqtt_port", 9783),
        "mqtt_user": cfg.get("mqtt_user", "test"),
        "mqtt_pass": cfg.get("mqtt_pass", "123456"),
        "modbus_slaves": cfg.get("modbus_slaves", []),
    }

    devs = cfg.get("devices", [])
    if devs:
        # 网关默认用第一个 relay 设备
        relay_dev = next((d for d in devs if d.get("role") == "relay"), devs[0])
        new_cfg["product_id"] = relay_dev.get("product_id", "relay-cc")
        new_cfg["device_id"] = relay_dev.get("device_id") or mac[-8:]
    else:
        new_cfg["product_id"] = "relay-cc"
        new_cfg["device_id"] = mac[-8:]

    print("[config] 已从 Day8 devices[] 格式迁移到 Day9 flat 格式")
    return new_cfg


def load():
    """读取配置; 不存在/损坏返回 None"""
    try:
        with open(CONFIG_PATH, "r") as f:
            cfg = json.loads(f.read())
        if not isinstance(cfg, dict):
            return None
    except OSError:
        return None
    except ValueError:
        print("[config] config.json 损坏, 视为未配网")
        return None

    # Day8 → Day9 迁移
    cfg = _migrate_day8(cfg)

    # 补全默认值 (新增字段)
    merged = defaults()
    merged.update(cfg)
    try:
        merged["mqtt_port"] = int(merged["mqtt_port"])
    except (ValueError, TypeError):
        merged["mqtt_port"] = DEFAULTS["mqtt_port"]
    if not merged.get("device_id"):
        merged["device_id"] = mac_address()[-8:]

    return merged


def is_ready(cfg):
    """配置是否足以进入正常运行模式"""
    if not cfg:
        return False
    for k in REQUIRED:
        if not str(cfg.get(k, "")).strip():
            return False
    if not cfg.get("product_id") or not cfg.get("device_id"):
        return False
    return True


def save(cfg):
    """写入配置 (先写临时文件再改名, 防止写一半掉电损坏)"""
    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w") as f:
        f.write(json.dumps(cfg))
    import os
    try:
        os.remove(CONFIG_PATH)
    except OSError:
        pass
    os.rename(tmp, CONFIG_PATH)
    print("[config] 已保存到", CONFIG_PATH)
