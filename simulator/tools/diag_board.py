import network, json, time, sys
wlan = network.WLAN(network.STA_IF)
print('WiFi:', wlan.isconnected(), wlan.ifconfig()[0] if wlan.isconnected() else 'N/A')
print()

# 重新连 WiFi (保险)
if not wlan.isconnected():
    cfg = json.load(open('/config.json'))
    wlan.connect(cfg['wifi_ssid'], cfg.get('wifi_pass',''))
    for i in range(20):
        time.sleep_ms(700)
        if wlan.isconnected():
            break
    print('Reconnected:', wlan.isconnected())

cfg = json.load(open('/config.json'))
print('Config:', cfg.get('product_id'), cfg.get('device_id'), cfg.get('mqtt_host'), cfg.get('mqtt_port'))

try:
    from umqtt.simple import MQTTClient
    cid = 'esp32-' + cfg.get('device_id','unknown') + '-diag'
    print('Connecting as', cid, '...')
    c = MQTTClient(cid, cfg['mqtt_host'], int(cfg['mqtt_port']),
                   cfg.get('mqtt_user',''), cfg.get('mqtt_pass',''), keepalive=30)
    ret = c.connect()
    print('MQTT OK ret=', ret)
    for i in range(3):
        c.publish('relay-cc/relaycc/properties/report',
                  json.dumps({'properties':{'diag_publish':i,'relay1':1}}), qos=0)
        print('  PUB', i)
        time.sleep_ms(300)
    c.disconnect()
    print('ALL OK! Check MQTTX relay-cc/relaycc/#')
except Exception as e:
    print('FAIL:', type(e).__name__, e)
    sys.print_exception(e)
