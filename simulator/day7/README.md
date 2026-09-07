# Day7: Modbus 采集网关

## 当天目标
在 Day5 继电器固件基础上，新增 Modbus TCP 主站能力，实现多从站时间片轮询采集，不阻塞继电器控制。

## 新增/修改文件清单

| 文件 | 状态 | 说明 |
|------|------|------|
| `modbus_gw.py` | **新增** | Modbus TCP 主站 + 时间片轮询调度器（324 行） |
| `app_config.py` | 修改 | DEFAULTS 新增 `modbus_enabled` / `modbus_slaves` |
| `ap_config.py` | 修改 | 配网页面新增 Modbus 采集配置卡片；修复 `ensure_ascii=False` MicroPython 兼容问题 |
| `main.py` | 修改 | 导入 modbus_gw、properties() 合并采集数据、mqtt_loop() 插入 poll_one() |

## 核心功能

- ✅ 多 Modbus TCP 从站支持（配置数组，每个从站独立 host/port/unit_id）
- ✅ **每个采集点独立周期**（period_ms，3s/5s/10s 可不同）
- ✅ 时间片轮询（每次 poll_one() 只采 1 个点，不阻塞）
- ✅ 冷却防阻塞（从站连续失败 3 次 → 30 秒内零阻塞跳过）
- ✅ 数据类型解码（uint16/int16/uint32/int32/float_be）
- ✅ scale 缩放系数（266 × 0.1 = 26.6°C）
- ✅ MQTT 上报合并（继电器状态 + Modbus 数据一条消息）
- ✅ 配网页面配置化（JSON 文本域，不用改代码）

## 与 Day5 对比

| 对比项 | Day5 | Day7 |
|--------|------|------|
| Modbus | ❌ 仅作为从站被读 | ✅ 主动作为主站读外部从站 |
| 采集能力 | 无 | 多从站 + 多寄存器 + 独立周期 |
| 上报字段 | relay1~4 | relay1~4 + temperature + humidity + ... |
| 配网页面 | WiFi + MQTT | WiFi + MQTT + **Modbus 配置卡片** |
| 新增代码量 | — | +409 行 |

## 配置示例（配网页面 Modbus 卡片填）

```json
[
  {
    "name": "温湿度传感器",
    "host": "192.168.30.85",
    "port": 5502,
    "unit_id": 7,
    "points": [
      {"addr": "0x0000", "key": "temperature", "period_ms": 3000, "count": 1, "type": "uint16", "scale": 0.1},
      {"addr": "0x0001", "key": "humidity",    "period_ms": 5000, "count": 1, "type": "uint16", "scale": 0.1}
    ]
  }
]
```

## 验收测试

1. PC 启动 `modbus_slave_sim.py 5502 7`
2. 板子配网启用 Modbus，指向 PC IP:5502
3. 串口应看到 `[modbus] temperature = 26.6`（带 scale）
4. 采集运行时按 SW1 → 继电器立即切换（非阻塞）
5. JetLinks 物模型 temperature/humidity 数据类型改为 double

## 运行指令

```powershell
# 上传新增/修改文件
cd simulator\esp32
python -m mpremote connect COM5 cp modbus_gw.py :/modbus_gw.py
python -m mpremote connect COM5 cp app_config.py :/app_config.py
python -m mpremote connect COM5 cp ap_config.py :/ap_config.py
python -m mpremote connect COM5 cp main.py :/main.py
python -m mpremote connect COM5 reset

# PC 端模拟器
cd simulator\tools
python modbus_slave_sim.py 5502 7

# 串口监控（双击 start_serial.bat 或手动）
python -c "import serial,time; s=serial.Serial('COM5',115200,timeout=1); time.sleep(2); print(s.read(s.in_waiting or 4096).decode('utf-8','replace')); s.close()"
```
