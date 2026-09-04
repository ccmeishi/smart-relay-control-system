"""配网模式 (Day5): 设备开 WiFi 热点, 手机网页填写配置

流程:
  1. 设备开放热点 RELAY-SETUP-xxxx (开放网络, 无密码)
  2. 手机连上热点, 浏览器打开 http://192.168.4.1
  3. 表单填写 WiFi、MQTT 信息(设备ID 默认 MAC), 提交
  4. 设备保存 /config.json 并自动重启进入正常模式
"""
import time
import socket
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
    def v(k):
        return str(cfg.get(k, ""))

    saved_banner = (
        '<div style="background:#1b5e20;color:#fff;padding:12px;border-radius:8px;'
        'margin-bottom:14px;font-size:15px">✅ 配置已保存，设备即将重启...'
        '请把手机切回正常 WiFi</div>'
    ) if saved else ""

    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>继电器设备配网</title>
<style>
body{font-family:Arial,"Microsoft YaHei",sans-serif;background:#0f172a;color:#e2e8f0;
 margin:0;padding:16px;max-width:520px;margin:0 auto}
h2{font-size:19px;margin:10px 0 4px}
.sub{color:#94a3b8;font-size:13px;margin-bottom:16px}
.card{background:#1e293b;border-radius:12px;padding:16px;margin-bottom:14px}
.card h3{font-size:15px;margin:0 0 12px;color:#60a5fa}
label{display:block;font-size:13px;margin:10px 0 4px;color:#cbd5e1}
input{width:100%;box-sizing:border-box;padding:11px;border-radius:8px;border:1px solid #334155;
 background:#0f172a;color:#f1f5f9;font-size:15px}
button{width:100%;padding:14px;border:0;border-radius:10px;background:#22c55e;color:#fff;
 font-size:17px;font-weight:bold;margin-top:8px}
.hint{font-size:12px;color:#64748b;margin-top:14px;line-height:1.6}
</style></head><body>
<h2>🔌 继电器设备配网</h2>
<div class="sub">设备热点: """ + AP_SSID_PREFIX + """xxxx &nbsp;|&nbsp; 配网完成后自动重启</div>
""" + saved_banner + """
<form method="POST" action="/save">
<div class="card">
<h3>📶 WiFi (设备要连的路由器/手机热点)</h3>
<label>WiFi 名称 (SSID)</label><input name="wifi_ssid" value='""" + v("wifi_ssid") + """' required>
<label>WiFi 密码</label><input name="wifi_pass" value='""" + v("wifi_pass") + """'>
</div>
<div class="card">
<h3>☁️ MQTT / JetLinks 平台</h3>
<label>MQTT 服务器 IP</label><input name="mqtt_host" value='""" + v("mqtt_host") + """' required>
<label>端口</label><input name="mqtt_port" value='""" + v("mqtt_port") + """' inputmode="numeric" required>
<label>账号</label><input name="mqtt_user" value='""" + v("mqtt_user") + """'>
<label>密码</label><input name="mqtt_pass" value='""" + v("mqtt_pass") + """'>
<label>产品ID (productId)</label><input name="product_id" value='""" + v("product_id") + """' required>
<label>设备ID (deviceId, 默认=MAC地址)</label><input name="device_id" value='""" + v("device_id") + """' required>
</div>
<button type="submit">保存并重启</button>
</form>
<div class="hint">提示: 设备ID 已默认填为本机 MAC 地址，无需修改；
如果平台里的设备不是这个 ID，请改成平台上的 deviceId。</div>
</body></html>"""


def start_ap():
    """开放设备热点, 返回热点名"""
    sta = network.WLAN(network.STA_IF)
    sta.active(False)                       # 配网时关掉 STA, 避免干扰
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
    """阻塞运行配网网页服务; 保存成功后自动重启。

    cfg=None 时优先读已有配置 /config.json (保留 device_id 等用户值),
    读不到才用 defaults() (device_id=MAC)。
    """
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
                # 按 Content-Length 收全表单
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
                print("[ap] 收到配置:", {k: (v if k != "wifi_pass" and k != "mqtt_pass" else "***")
                                        for k, v in form.items()})
                new_cfg = dict(cfg)              # 基于当前配置 (保留未改字段)
                new_cfg.update({k: form.get(k, "") for k in (
                    "wifi_ssid", "wifi_pass", "mqtt_host", "mqtt_user",
                    "mqtt_pass", "product_id", "device_id")})
                try:
                    new_cfg["mqtt_port"] = int(form.get("mqtt_port", "9783"))
                except ValueError:
                    new_cfg["mqtt_port"] = 9783
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
