"""用户配置持久化 (Day5 配网固件)

配置保存在板子 Flash 的 /config.json, 断电不丢;
首次使用或 SW1 长按 5 秒进入配网模式时, 由 ap_config.py 网页写入。
relay_hw.py 里的硬件常量(继电器/按键 GPIO)是板级固定接线, 不在这里。
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
    "product_id": "relay-cc",
    "device_id": "",          # 空 -> 首次加载时自动填 MAC
}

# 正常运行必须有的字段 (缺任何一个都视为未配网)
REQUIRED = ("wifi_ssid", "mqtt_host", "device_id")


def mac_address():
    """返回 12 位小写 MAC 十六进制, 如 'a4cf12c8b190'"""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    return ubinascii.hexlify(wlan.config("mac")).decode()


def defaults():
    d = dict(DEFAULTS)
    d["device_id"] = mac_address()
    return d


def load():
    """读取配置; 不存在/损坏返回 None。合法配置会补全缺失字段并强制类型。"""
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

    # 与默认值合并, 补齐后续版本新增字段
    merged = defaults()
    merged.update(cfg)
    try:
        merged["mqtt_port"] = int(merged["mqtt_port"])
    except (ValueError, TypeError):
        merged["mqtt_port"] = DEFAULTS["mqtt_port"]
    if not merged.get("device_id"):
        merged["device_id"] = mac_address()
    return merged


def is_ready(cfg):
    """配置是否足以进入正常运行模式"""
    if not cfg:
        return False
    return all(str(cfg.get(k, "")).strip() for k in REQUIRED)


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
