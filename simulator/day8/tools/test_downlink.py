import paho.mqtt.publish as publish
import json, time

msg = json.dumps({"messageId":"t1","properties":{"relay1":0}})
print("PUBLISH -> relay-cc/relaycc/properties/write")
print("  body:", msg)
publish.single(
    "relay-cc/relaycc/properties/write",
    msg,
    hostname="172.16.4.211", port=9783,
    auth={"username":"test","password":"123456"}
)
print("OK! Did you hear relay click? Check MQTTX for properties/report update.")
time.sleep(2)

msg2 = json.dumps({"messageId":"t2","functionId":"set_relay","inputs":{"继电器编号":"1","状态":1}})
print("\nPUBLISH -> relay-cc/relaycc/function/invoke")
print("  body:", msg2)
publish.single(
    "relay-cc/relaycc/function/invoke",
    msg2,
    hostname="172.16.4.211", port=9783,
    auth={"username":"test","password":"123456"}
)
print("OK! Did you hear relay click again?")
