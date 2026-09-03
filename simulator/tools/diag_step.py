"""分步 checkpoint 诊断: 订阅 relay 相关 topic 3 秒"""
import time
import paho.mqtt.client as mqtt

def cp(msg):
    with open('diag_step.txt', 'a', encoding='utf-8') as f:
        f.write(f'[{time.strftime("%H:%M:%S")}] {msg}\n')

cp('step1: 开始, import paho 成功')
got = []

def on_msg(client, userdata, m):
    got.append((m.topic, m.payload[:100].decode('utf-8', 'ignore')))
    cp(f'msg: {m.topic}')

c = mqtt.Client()
c.username_pw_set('test', '123456')
c.on_message = on_msg
cp('step2: client 创建')
c.connect('172.16.4.211', 9783, 10)
cp('step3: connect 完成')
c.subscribe('sensor-cc/#', 1)
c.subscribe('/sensor-cc/#', 1)
cp('step4: subscribe 完成')
c.loop_start()
t = time.time()
while time.time() - t < 3:
    time.sleep(0.2)
c.loop_stop()
cp(f'step5: 监听 3 秒结束, 收到 {len(got)} 条')
for topic, payload in got[:10]:
    cp(f'  {topic}  {payload}')
