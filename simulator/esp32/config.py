"""ESP32 四路继电器板 - 全局配置 (两条路线共用)

使用前必改:
  1. WIFI_SSID / WIFI_PASS      -> 改成实验室 WiFi 或手机热点
  2. RELAY_PINS                 -> 改成卖家资料里 4 路继电器实际接的 GPIO
  3. RELAY_ACTIVE_LOW           -> 低电平触发 True / 高电平触发 False (看商品页或例程)
"""

# ---------- WiFi ----------
WIFI_SSID = "Office-WiFi"       # 实验室 WiFi
WIFI_PASS = "yh82922868"

# ---------- 路线A: MQTT 直连 EMQX -> JetLinks ----------
MQTT_HOST = "172.16.4.211"
MQTT_PORT = 9783
MQTT_USER = "test"
MQTT_PASS = "123456"
MQTT_CLIENT_ID = "relaycc-esp32"      # 必须与 PC 模拟器 relaycc-jl 不同, 避免互踢
PRODUCT_ID = "relay-cc"               # 沿用平台现有产品, 平台配置零改动
DEVICE_ID = "relaycc"

# ---------- 继电器硬件 ----------
RELAY_PINS = [3, 4, 5, 7]             # 卖家图: 四路继电器从左至右 IO3/IO4/IO5/IO7
RELAY_ACTIVE_LOW = False              # 实测: UI开=亮/关=灭, 上电全亮说明是高电平触发

# ---------- 路线B: Modbus TCP 从站 ----------
MODBUS_PORT = 502
MODBUS_UNIT_ID = 7                    # 与实验室从站一致 (7组专用)
