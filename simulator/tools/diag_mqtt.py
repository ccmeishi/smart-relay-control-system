"""临时诊断: 监听 EMQX 上 relay-cc 相关消息, 15 秒后打印结果"""
import time
import paho.mqtt.client as mqtt

out = []

def on_msg(client, userdata, m):
    out.append((time.strftime('%H:%M:%S'), m.topic, m.payload[:120].decode('utf-8', 'ignore')))

c = mqtt.Client()
c.username_pw_set('test', '123456')
c.on_message = on_msg
c.connect('172.16.4.211', 9783, 60)
c.subscribe('#', 2)
out.append('订阅 # 监听 8 秒...')
t = time.time()
c.loop_start()
while time.time() - t < 8:
    time.sleep(0.3)
c.loop_stop()

relay = [x for x in out if 'relay' in x[1]]
other = [x for x in out if 'relay' not in x[1]]
lines = [f'共收到 {len(out)} 条, 其中 relay 相关 {len(relay)} 条:']
for ts, topic, payload in relay[:20]:
    lines.append(f'  [{ts}] {topic}  {payload}')
lines.append(f'其他消息 {len(other)} 条 (topic 样例):')
seen = set()
for ts, topic, payload in other:
    if topic not in seen:
        seen.add(topic)
        lines.append(f'  [{ts}] {topic}  {payload[:60]}')

with open('diag_result.txt', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print('done')
