"""配网模式 (Day9 网关版): 设备开 WiFi 热点, 手机网页填写配置

流程:
  1. 设备开放热点 RELAY-SETUP-xxxx (开放网络, 无密码)
  2. 手机连上热点, 浏览器打开 http://192.168.4.1
  3. 表单填写 WiFi + MQTT + 网关产品 + Modbus 多寄存器
  4. 设备保存 /config.json 并自动重启

Day9 架构:
  ESP32 只连 1 个网关产品, 所有数据汇总上报到网关 topic,
  Python Bridge 服务负责按 routing table 拆分转发到多虚拟产品。
"""
import time
import socket
import json
import network
import machine

import app_config

AP_IP = "192.168.4.1"
AP_SSID_PREFIX = "RELAY-SETUP-"


def _unquote(s):
    """application/x-www-form-urlencoded 解码"""
    s = s.replace("+", " ")
    out = ""
    i = 0
    while i < len(s):
        if s[i] == "%" and i + 2 < len(s):
            try:
                out += chr(int(s[i + 1:i + 3], 16))
                i += 3
                continue
            except ValueError:
                pass
        out += s[i]
        i += 1
    return out


def _parse_form(body):
    form = {}
    for pair in body.split("&"):
        if "=" in pair:
            k, v = pair.split("=", 1)
            form[_unquote(k)] = _unquote(v).strip()
    return form


def _html_form(cfg, saved=False):
    saved_banner = (
        '<div style="background:#1b5e20;color:#fff;padding:12px;border-radius:8px;'
        'margin-bottom:14px;font-size:15px">✅ 配置已保存，设备即将重启...'
        '请把手机切回正常 WiFi</div>'
    ) if saved else ""

    pid = str(cfg.get("product_id", "relay-cc"))
    did = str(cfg.get("device_id", ""))

    mb_slaves = cfg.get("modbus_slaves", [])
    if mb_slaves:
        mb_json = json.dumps(mb_slaves)
    else:
        mb_json = json.dumps(app_config.DEFAULTS["modbus_slaves"])

    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>智能网关配网</title>
<style>
body{font-family:Arial,"Microsoft YaHei",sans-serif;background:#0f172a;color:#e2e8f0;
 margin:0;padding:16px;max-width:560px;margin:0 auto}
h2{font-size:19px;margin:10px 0 4px}
.sub{color:#94a3b8;font-size:13px;margin-bottom:16px}
.card{background:#1e293b;border-radius:12px;padding:16px;margin-bottom:14px}
.card h3{font-size:15px;margin:0 0 12px;color:#60a5fa}
label{display:block;font-size:13px;margin:10px 0 4px;color:#cbd5e1}
input,textarea,select{width:100%;box-sizing:border-box;padding:11px;border-radius:8px;border:1px solid #334155;
 background:#0f172a;color:#f1f5f9;font-size:15px;font-family:inherit}
textarea{font-family:monospace;font-size:13px;min-height:180px;resize:vertical}
button{width:100%;padding:14px;border:0;border-radius:10px;background:#22c55e;color:#fff;
 font-size:17px;font-weight:bold;margin-top:8px}
.hint{font-size:12px;color:#64748b;margin-top:14px;line-height:1.6}
.row{display:flex;gap:10px}
.row>div{flex:1}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:bold;background:#dc2626;color:#fff}
</style></head><body>
<h2>🔌 智能网关配网 (Day9)</h2>
<div class="sub">单网关 → Python Bridge → 多虚拟产品 (门锁/灯/空调/温湿度/人体/烟雾)</div>
""" + saved_banner + """
<form method="POST" action="/save">

<div class="card">
<h3>📶 WiFi (设备要连的路由器/手机热点)</h3>
<div class="row">
<div><label>WiFi 名称 (SSID)</label><input name="wifi_ssid" value='""" + str(cfg.get("wifi_ssid", "")) + """' required></div>
<div><label>WiFi 密码</label><input name="wifi_pass" value='""" + str(cfg.get("wifi_pass", "")) + """'></div>
</div>
</div>

<div class="card">
<h3>☁️ JetLinks / EMQX MQTT</h3>
<div class="row">
<div><label>MQTT 服务器 IP</label><input name="mqtt_host" value='""" + str(cfg.get("mqtt_host", "172.16.4.211")) + """' required></div>
<div><label>端口</label><input name="mqtt_port" value='""" + str(cfg.get("mqtt_port", "9783")) + """' required></div>
</div>
<div class="row">
<div><label>账号</label><input name="mqtt_user" value='""" + str(cfg.get("mqtt_user", "test")) + """'></div>
<div><label>密码</label><input name="mqtt_pass" value='""" + str(cfg.get("mqtt_pass", "123456")) + """'></div>
</div>
</div>

<div class="card">
<h3><span class="badge">网关</span> 📡 JetLinks 网关产品</h3>
<div class="row">
<div><label>产品ID (productId)</label><input name="product_id" value='""" + pid + """' required></div>
<div><label>设备ID (deviceId)</label><input name="device_id" value='""" + did + """' required></div>
</div>
<div class="hint">
ESP32 作为单网关上报所有数据到此产品的 properties/report,
Python Bridge 订阅此 topic 后按 routing table 拆分到多虚拟产品。<br>
网关产品物模型需包含所有属性: relay1~4, temperature, humidity, human, smoke, current, voltage
</div>
</div>

<div class="card">
<h3>📝 Modbus TCP 采集点 (JSON)</h3>
<textarea name="modbus_slaves" placeholder='[{"host":"192.168.30.100","port":502,"unit_id":1,"points":[{"addr":"0x0000","key":"temperature","period_ms":3000,"count":1,"type":"uint16","scale":0.1}]}]'>""" + mb_json + """</textarea>
<div class="hint">
<b>type:</b> uint16 / int16 (1寄存器), uint32 / int32 (2寄存器), float_be (2寄存器大端浮点)<br>
<b>scale:</b> 寄存器值 × scale = 上报值, 如 scale=0.1 表示 266 → 26.6<br>
<b>key 命名规则:</b> Bridge 的 UP_ROUTING 用 key 路由, 常用 key: temperature humidity human smoke current voltage<br>
<b>硬件:</b> 每路寄存器是 Modbus 从站模拟器上的一个"点", 可以多开几个寄存器模拟多传感器
</div>
</div>

<button type="submit">💾 保存并重启</button>
</form>
<div class="hint">
保存后设备自动重启。重启完请启动 Python Bridge:<br>
  python simulator/tools/gateway_bridge.py
</div>
</body></html>"""


def start_ap():
    """开放设备热点, 返回热点名"""
    sta = network.WLAN(network.STA_IF)
    sta.active(False)
    ap = network.WLAN(network.AP_IF)
    ap.active(False)
    time.sleep_ms(200)
    ap.active(True)
    mac = ""
    try:
        import ubinascii
        mac = ubinascii.hexlify(ap.config("mac")).decode()[-4:]
    except Exception:
        pass
    ssid = AP_SSID_PREFIX + mac
    ap.config(essid=ssid, authmode=network.AUTH_OPEN)
    ap.ifconfig((AP_IP, "255.255.255.0", AP_IP, AP_IP))
    print("[ap] 热点已开放: %s (开放网络)" % ssid)
    print("[ap] 手机连热点后打开 http://%s" % AP_IP)
    return ssid


def run(cfg=None):
    """阻塞运行配网网页服务; 保存成功后自动重启。"""
    if cfg is None:
        cfg = app_config.load() or app_config.defaults()
    start_ap()

    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", 80))
    srv.listen(3)
    srv.settimeout(1)

    saved = False
    while True:
        if saved:
            time.sleep(2)
            machine.reset()
        try:
            cl, _addr = srv.accept()
        except OSError:
            continue
        try:
            cl.settimeout(5)
            req = cl.recv(2048)
            if not req:
                cl.close()
                continue
            text = req.decode("utf-8", "replace")
            line = text.split("\r\n", 1)[0]
            if "POST /save" in line:
                body = text.split("\r\n\r\n", 1)[1] if "\r\n\r\n" in text else ""
                length = 0
                for h in text.split("\r\n"):
                    if h.lower().startswith("content-length:"):
                        length = int(h.split(":")[1].strip())
                while len(body.encode()) < length:
                    chunk = cl.recv(1024)
                    if not chunk:
                        break
                    body += chunk.decode("utf-8", "replace")
                form = _parse_form(body)
                print("[ap] 收到配置:", {k: (v if k not in ("wifi_pass", "mqtt_pass", "wifi_ssid") else "***")
                                        for k, v in form.items()})

                new_cfg = dict(cfg)
                new_cfg["wifi_ssid"] = form.get("wifi_ssid", "")
                new_cfg["wifi_pass"] = form.get("wifi_pass", "")
                new_cfg["mqtt_host"] = form.get("mqtt_host", "172.16.4.211")
                try:
                    new_cfg["mqtt_port"] = int(form.get("mqtt_port", "9783"))
                except ValueError:
                    new_cfg["mqtt_port"] = 9783
                new_cfg["mqtt_user"] = form.get("mqtt_user", "test")
                new_cfg["mqtt_pass"] = form.get("mqtt_pass", "123456")

                # Day9 flat 格式: 网关产品 + 设备
                new_cfg["product_id"] = form.get("product_id", "relay-cc")
                new_cfg["device_id"] = form.get("device_id", "").strip()
                if not new_cfg["device_id"]:
                    import ubinascii
                    w = network.WLAN(network.STA_IF)
                    new_cfg["device_id"] = ubinascii.hexlify(w.config("mac")).decode()[-8:]

                # Modbus 配置
                mb_raw = form.get("modbus_slaves", "").strip()
                if mb_raw:
                    try:
                        mb_slaves = json.loads(mb_raw)
                        if isinstance(mb_slaves, list):
                            new_cfg["modbus_slaves"] = mb_slaves
                        else:
                            new_cfg["modbus_slaves"] = []
                    except ValueError:
                        print("[ap] Modbus JSON 解析失败, 忽略")
                        new_cfg["modbus_slaves"] = []
                else:
                    new_cfg["modbus_slaves"] = []

                app_config.save(new_cfg)
                html = _html_form(new_cfg, saved=True)
                cl.send("HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                        "Connection: close\r\n\r\n" + html)
                saved = True
            else:
                html = _html_form(cfg)
                cl.send("HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                        "Connection: close\r\n\r\n" + html)
        except Exception as e:
            print("[ap] 请求处理异常:", e)
        finally:
            try:
                cl.close()
            except Exception:
                pass
