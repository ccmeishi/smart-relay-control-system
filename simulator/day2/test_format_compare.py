"""Day2 格式对比测试脚本

测试两种数据格式的接入流程:
  方式一: 非标准格式 (Day1 原始报文) → EMQX 规则转换 → JetLinks
  方式二: 标准格式 (JetLinks 官方协议) → 设备直连 → JetLinks

运行: python test_format_compare.py
依赖: pip install paho-mqtt==1.6.1

启动后会:
  1. 打印两种格式的 payload 对比表格
  2. 同时往两个 topic 发布一条测试数据
  3. 提示在 MQTTX / JetLinks 观察结果
  4. 每 5 秒循环发布, 10 次后退出
"""

import json
import time
import uuid

import paho.mqtt.client as mqtt

# ============================================================
# 连接配置
# ============================================================
MQTT_HOST = "172.16.4.211"
MQTT_PORT = 9783
MQTT_USER = "test"
MQTT_PASS = "123456"

# 方式一: Day1 原始 topic (非标准格式, 由 EMQX 规则转换)
TOPIC_ORIGINAL = "device/sensor/sevengroup"

# 方式二: JetLinks 官方 topic (标准格式, 设备直连)
TOPIC_JETLINKS = "/sensor-cc/sensorcc/properties/report"


def gen_msg_id():
    return str(uuid.uuid4())[:16]


def build_original_payload(temp, hum):
    """方式一: Day1 非标准格式"""
    return {
        "type": "data",
        "temperature": temp,
        "humidity": hum,
        "registers": [int(temp * 10), int(hum * 10)],
        "deviceId": "sensor_sevengroup",
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def build_jetlinks_payload(temp, hum):
    """方式二: JetLinks 官方标准格式"""
    return {
        "timestamp": int(time.time() * 1000),
        "messageId": gen_msg_id(),
        "properties": {
            "temperature": temp,
            "humidity": hum,
        },
    }


def print_comparison():
    """打印两种格式的字段对比"""
    temp = 25.3
    hum = 56.7

    orig = build_original_payload(temp, hum)
    jl = build_jetlinks_payload(temp, hum)

    print()
    print("=" * 72)
    print("  Day2 两种数据格式对比")
    print("=" * 72)

    print(f"""
  ┌─────────────────────────────────────────────────────────────────────┐
  │  方式一: 非标准格式 (Day1 原始报文, EMQX 规则转换接入 JetLinks)      │
  ├─────────────────────────────────────────────────────────────────────┤
  │  Topic : {TOPIC_ORIGINAL:<62} │
  │  Payload: {json.dumps(orig, ensure_ascii=False)[:62]} │
  └─────────────────────────────────────────────────────────────────────┘
  特点: 设备固件无需修改, 旧设备即可接入新平台
  链路: 设备 → EMQX → [规则转换] → JetLinks
""")

    print(f"""
  ┌─────────────────────────────────────────────────────────────────────┐
  │  方式二: 标准格式 (JetLinks 官方协议, 设备直连 JetLinks)             │
  ├─────────────────────────────────────────────────────────────────────┤
  │  Topic : {TOPIC_JETLINKS:<62} │
  │  Payload: {json.dumps(jl, ensure_ascii=False)[:62]} │
  └─────────────────────────────────────────────────────────────────────┘
  特点: 完全符合 JetLinks 物模型定义, 支持双向通信
  链路: 设备 → EMQX → JetLinks (JetLinks 作为 MQTT 客户端订阅)
""")

    print("  字段对比:")
    print("  ┌───────────────┬──────────────────────────┬──────────────────────────────┐")
    print("  │ 字段           │ 方式一 (非标准)           │ 方式二 (标准 JetLinks)       │")
    print("  ├───────────────┼──────────────────────────┼──────────────────────────────┤")
    print(f"  │ 温度字段       │ temperature={temp}       │ properties.temperature={temp}│")
    print(f"  │ 湿度字段       │ humidity={hum}           │ properties.humidity={hum}    │")
    print("  │ 时间戳         │ ts (ISO 字符串)          │ timestamp (毫秒整数)          │")
    print("  │ 消息 ID        │ 无                       │ messageId (UUID)              │")
    print("  │ 包类型标识     │ type=data                │ 无 (topic 隐含)               │")
    print("  │ 设备标识       │ deviceId                 │ topic 中的 productId/deviceId │")
    print("  └───────────────┴──────────────────────────┴──────────────────────────────┘")
    print()


def main():
    print_comparison()

    # 连接 MQTT
    client = mqtt.Client(client_id="format_compare_test", clean_session=True)
    client.username_pw_set(MQTT_USER, MQTT_PASS)
    client.connect(MQTT_HOST, MQTT_PORT, keepalive=30)
    client.loop_start()

    print(f"  已连接 {MQTT_HOST}:{MQTT_PORT}")
    print(f"  发布频率: 每 5 秒 1 次, 共 10 次")
    print()
    print("  测试前请确保:")
    print("    1. EMQX 规则已启用 (规则 SQL: SELECT * FROM \"device/sensor/sevengroup\")")
    print("    2. JetLinks 设备 sensor-cc/sensorcc 在线")
    print("    3. MQTTX 已订阅以下 topic 观察结果")
    print()
    print("  Ctrl+C 随时退出\n")

    try:
        for i in range(10):
            temp = round(25.0 + (i * 0.5), 1)
            hum = round(55.0 + (i * 0.3), 1)

            # 方式一: 原始格式
            orig_payload = json.dumps(build_original_payload(temp, hum), ensure_ascii=False)
            r1 = client.publish(TOPIC_ORIGINAL, orig_payload, qos=1)

            # 方式二: JetLinks 标准格式
            jl_payload = json.dumps(build_jetlinks_payload(temp, hum), ensure_ascii=False)
            r2 = client.publish(TOPIC_JETLINKS, jl_payload, qos=1)

            ts = time.strftime("%H:%M:%S")
            ok1 = "✓" if r1.rc == 0 else "✗"
            ok2 = "✓" if r2.rc == 0 else "✗"

            print(f"  [{ts}] #{i+1:02d} 温度={temp}°C 湿度={hum}%RH")
            print(f"         方式一 → {TOPIC_ORIGINAL}  {ok1}")
            print(f"         方式二 → {TOPIC_JETLINKS}  {ok2}")

            time.sleep(5)

        print("\n  ✅ 测试完成, 请在 JetLinks 运行状态页确认两种方式都收到数据\n")

    except KeyboardInterrupt:
        print("\n  已中断\n")
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
