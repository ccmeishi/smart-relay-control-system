"""发两条温湿度测试消息(带/不带斜杠) + 监听验证 - 单连接版"""
import json
import time
import paho.mqtt.client as mqtt

def cp(msg):
    with open('diag_step.txt', 'a', encoding='utf-8') as f:
        f.write(f'[{time.strftime("%H:%M:%S")}] {msg}\n')

got = []

def on_msg(client, userdata, m):
    got.append((m.topic, m.payload[:80].decode('utf-8', 'ignore')))

def mkpayload(mid, temp, hum):
    return {'timestamp': int(time.time() * 1000), 'messageId': mid,
            'properties': {'temperature': temp, 'humidity': hum}}

cp('=== 对比实验 v2 开始 ===')
c = mqtt.Client()
c.username_pw_set('test', '123456')
c.on_message = on_msg
c.connect('172.16.4.211', 9783, 10)
cp('connect 完成')
c.subscribe('sensor-cc/#', 1)
c.subscribe('/sensor-cc/#', 1)
c.loop_start()
time.sleep(1)
r1 = c.publish('/sensor-cc/sensorcc/properties/report',
               json.dumps(mkpayload('diag-slash', 25.5, 56.7), ensure_ascii=False), qos=1)
cp(f'publish 带斜杠 topic 已调用 rc={r1.rc}')
r2 = c.publish('sensor-cc/sensorcc/properties/report',
               json.dumps(mkpayload('diag-noslash', 26.5, 57.7), ensure_ascii=False), qos=1)
cp(f'publish 不带斜杠 topic 已调用 rc={r2.rc}')
time.sleep(3)
c.loop_stop()
cp(f'监听结束, 收到 {len(got)} 条:')
for topic, payload in got[:6]:
    cp(f'  {topic}  {payload}')
