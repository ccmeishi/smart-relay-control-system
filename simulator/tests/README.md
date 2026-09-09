# 测试说明

## 跑测试

```powershell
# 1. 安装依赖
cd E:\shixiproject\traeproject1\simulator
pip install -r requirements-dev.txt

# 2. 跑全部测试
pytest tests/

# 3. 跑某个测试文件
pytest tests/test_modbus_slave_sim.py -v

# 4. 跑某个测试类
pytest tests/test_modbus_slave_sim.py::TestCurrentIncrement -v

# 5. 跑单个测试
pytest tests/test_modbus_slave_sim.py::TestReadHoldingRegisters::test_read_temperature_register0 -v
```

## 覆盖范围

| 文件 | 用例 | 覆盖 | 类型 |
|---|---|---|---|
| `test_modbus_slave_sim.py` | 22 | FC 0x03/0x06、unit_id 过滤、drift、并发 | 真实进程 + pymodbus 集成 |
| `test_gateway_bridge.py` | 28 | 路由表自洽、上行拆分、下行 write/invoke、reply 闭环 | mock MQTT 纯逻辑 |
| `test_sensor_simulator.py` | 41 | 寄存器解析、JSON IO、MQTT 命令解析、payload 契约 | mock + tmp_path |
| `test_protocol_consistency.py` | 21 | 三处寄存器布局/连接配置一致性 | 纯文件解析 |
| `test_mqtt_integration.py` | 7 | 真实 broker + bridge + 模拟 ESP32/平台 端到端 | amqtt broker + paho-mqtt 客户端 |
| `test_esp32_modbus_gw.py` | 40 | MBAP 编解码、5 种寄存器类型、SlaveConn 读写+冷却、ModbusGateway 调度、config 常量+JSON 一致性 | mock time/socket（不依赖 ESP32 板子） |

合计 **159 个测试用例**，~64 秒跑完。

## esp32 mock 测试说明

`test_esp32_modbus_gw.py` 用 `FakeTime` + `FakeSocket` 替换 MicroPython 的 `time` 和 `socket` 模块，让 `modbus_gw.py` 在普通 PC Python 环境下也能跑。

设计上：
- **`modbus_gw.py` 顶层纯函数** (`_mbap`/`_parse_response`/`_decode_registers`) 完全可测
- **连接层** (`_SlaveConn`) 通过 monkey-patch `socket.socket` 让 connect/sendall/recv 可控
- **`ModbusGateway` 调度** 通过 `FakeTime.advance()` 推进时间片
- **未覆盖**: `relay_hw.py`（依赖 `machine.Pin`/`Timer`）、`app_config.py`（依赖 `network`/`ubinascii`）——这些只有真机 / MicroPython 解释器才能跑

已知小坑（已记录在测试的注释里）：
> `_SlaveConn.write_holding` 只 `recv(7)` 字节，但 `_parse_response` 严格要求 `len(frame) >= 6 + length`，7 字节头永远不满足。
> 当前测试只验证 sendall PDU 内容正确；写响应的成功路径只能在真机或集成测试里覆盖。

## 跑测试的硬件要求

- Python 3.8+（推荐 3.11+）
- 一个空闲的临时 TCP 端口
- **不需要** ESP32 板子
- **不需要** MQTT broker
- **不需要** JetLinks 平台账号

测试会启动一个真实的 `modbus_slave_sim.py` 进程（绑定 127.0.0.1 随机端口），用 pymodbus 做集成测试，跑完自动清理。
gateway_bridge 测试用 `unittest.mock` 替换 MQTT 客户端，不需要真实 broker。
esp32 mock 测试用 `FakeTime`/`FakeSocket` 替换 MicroPython 模块，不需要 ESP32。

## 故障排查

| 现象 | 原因 | 解决 |
|---|---|---|
| `socket.gaierror` | 网络问题 | 测试只用 127.0.0.1，不应触发 |
| `subprocess ... No such file` | 路径不对 | 检查 `conftest.py` 里的 `SLAVE_SCRIPT` 路径 |
| 端口被占用 | 上次测试未清理 | 测试用临时端口，不会冲突；如仍报错，杀掉残留的 modbus_slave_sim 进程 |
| pymodbus API 不匹配 | 版本差异 | 项目锁了 `pymodbus>=3.6.0,<4.0` |
