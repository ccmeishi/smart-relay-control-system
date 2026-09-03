"""快速诊断: 抓 JetLinks 下行命令 + 检查模拟器上报是否被接收"""
import paho.mqtt.client as mqtt
import json, time

GOT = []

def on_msg(c, u, m):
    text = m.payload[:300].decode('utf-8', 'ignore')
    GOT.append({'topic': m.topic, 'payload': text})
    print(f"\n[{time.strftime('%H:%M:%S')}] {m.topic}")
    print(f"  {text}")

def on_connect(c, u, f, rc):
    if rc == 0:
        print(f"[{time.strftime('%H:%M:%S')}] 已连接, 订阅 # ...")
        c.subscribe("#", 1)
        print("  监听 30 秒... 去 JetLinks 点功能调用/属性编辑\n")

c = mqtt.Client("diag-quick-" + str(int(time.time())))
c.username_pw_set("test", "123456")
c.on_connect = on_connect
c.on_message = on_msg
c.connect("172.16.4.211", 9783, 10)
c.loop_start()

time.sleep(30)
c.loop_stop()

print(f"\n=== 总共抓到 {len(GOT)} 条消息 ===")
for g in GOT:
    print(f"  {g['topic']}")
