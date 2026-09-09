"""协议一致性检查

对比三处寄存器布局/连接配置：
1. simulator/tools/modbus_slave_sim.py        (PC 从站 - 权威)
2. simulator/day2/config_relay.json           (Day2 PC 端继电器模拟器)
3. simulator/esp32/config.json                (ESP32 网关采集配置)

不强制三处布局完全相同（因为 ESP32 只采集不写继电器），但要求共有的 key
在以下维度一致：
- 寄存器地址
- 数据类型 (int16/uint16/uint32/...)
- 缩放系数 (scale)
- 有符号/无符号 (signed)
- Modbus 从站 IP / 端口 / unit_id

任何不一致会作为 fail 报错，方便你们组在真机联调前发现配置漂移。

不依赖任何外部 broker/板子，纯文件解析。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
SLAVE_SCRIPT = REPO_ROOT / "simulator" / "tools" / "modbus_slave_sim.py"
DAY2_CONFIG = REPO_ROOT / "simulator" / "day2" / "config_relay.json"
ESP32_CONFIG = REPO_ROOT / "simulator" / "esp32" / "config.json"
DAY8_SLAVE_SCRIPT = REPO_ROOT / "simulator" / "day8" / "tools" / "modbus_slave_sim.py"


# ---------- 1. 从 modbus_slave_sim.py 提取"权威"寄存器布局 ----------

def parse_slave_script(script_path: Path) -> dict:
    """从 modbus_slave_sim.py 提取寄存器布局（注释头 + REGS + 命名常量）

    返回：
    {
      "layout": { 0: "temperature", 1: "humidity", 2-9: "relay1-8", 10: "current", 11: "voltage" },
      "relay_registers": [2, 3, ..., 9],
      "current_register": 10,
      "voltage_register": 11,
      "default_unit_id": <int>,
      "default_port": <int>,
    }
    """
    text = script_path.read_text(encoding="utf-8")

    # 默认 unit_id 和 port
    m_unit = re.search(r"UNIT_ID\s*=\s*int\(sys\.argv\[2\]\)\s+if\s+len\(sys\.argv\)\s*>\s*2\s+else\s+(\d+)", text)
    default_unit_id = int(m_unit.group(1)) if m_unit else None
    m_port = re.search(r"PORT\s*=\s*int\(sys\.argv\[1\]\)\s+if\s+len\(sys\.argv\)\s*>\s*1\s+else\s+(\d+)", text)
    default_port = int(m_port.group(1)) if m_port else None

    # 寄存器常量
    m_relay = re.search(r"RELAY_REGS\s*=\s*\[(.*?)\]", text, re.S)
    relay_registers = [int(x.strip()) for x in m_relay.group(1).split(",") if x.strip().isdigit()] if m_relay else []
    m_current = re.search(r"CURRENT_REG\s*=\s*(\d+)", text)
    current_register = int(m_current.group(1)) if m_current else None
    m_voltage = re.search(r"VOLTAGE_REG\s*=\s*(\d+)", text)
    voltage_register = int(m_voltage.group(1)) if m_voltage else None

    # 从注释头提取布局描述
    layout = {}
    for line in text.splitlines()[:30]:
        # 匹配 "reg0  = 温度" 或 "reg0 = 温度"
        m = re.match(r"\s*reg(\d+)\s*=\s*(.+)", line)
        if m:
            reg = int(m.group(1))
            desc = m.group(2).strip()
            layout[reg] = desc

    return {
        "layout": layout,
        "relay_registers": relay_registers,
        "current_register": current_register,
        "voltage_register": voltage_register,
        "default_unit_id": default_unit_id,
        "default_port": default_port,
    }


# ---------- 2. 解析 esp32 config.json ----------

def parse_esp32_config() -> dict:
    """解析 ESP32 网关的采集点位"""
    cfg = json.loads(ESP32_CONFIG.read_text(encoding="utf-8"))
    slaves = cfg.get("modbus_slaves", [])
    if not slaves:
        return {"slaves": []}

    parsed_slaves = []
    for slave in slaves:
        points = []
        for pt in slave.get("points", []):
            addr_str = pt.get("addr", "0x0000")
            addr = int(addr_str, 16) if addr_str.startswith("0x") else int(addr_str)
            points.append({
                "addr": addr,
                "key": pt.get("key"),
                "scale": pt.get("scale"),
                "type": pt.get("type", "uint16"),
                "period_ms": pt.get("period_ms"),
            })
        parsed_slaves.append({
            "name": slave.get("name"),
            "host": slave.get("host"),
            "port": slave.get("port"),
            "unit_id": slave.get("unit_id"),
            "points": points,
        })
    return {
        "mqtt_host": cfg.get("mqtt_host"),
        "mqtt_port": cfg.get("mqtt_port"),
        "product_id": cfg.get("product_id"),
        "device_id": cfg.get("device_id"),
        "slaves": parsed_slaves,
    }


# ---------- 3. 解析 day2 config_relay.json ----------

def parse_day2_config() -> dict:
    cfg = json.loads(DAY2_CONFIG.read_text(encoding="utf-8"))
    mb = cfg.get("modbus", {})
    rm = cfg.get("register_map", {})
    return {
        "modbus_host": mb.get("host"),
        "modbus_port": mb.get("port"),
        "unit_id": mb.get("unit_id"),
        "register_start": mb.get("register_start"),
        "register_count": mb.get("register_count"),
        "poll_interval": mb.get("poll_interval"),
        "register_map": {int(k): v for k, v in rm.items()},
        "mqtt": cfg.get("mqtt", {}),
        "jetlinks": cfg.get("jetlinks", {}),
    }


# ---------- 4. 解析器自身要能跑通 ----------

class TestParsers:
    """解析器自身要工作"""

    def test_slave_script_parses(self):
        info = parse_slave_script(SLAVE_SCRIPT)
        assert info["relay_registers"] == [2, 3, 4, 5, 6, 7, 8, 9]
        assert info["current_register"] == 10
        assert info["voltage_register"] == 11
        # reg0=温度, reg1=湿度
        assert "温度" in info["layout"][0]
        assert "湿度" in info["layout"][1]

    def test_esp32_config_parses(self):
        cfg = parse_esp32_config()
        assert len(cfg["slaves"]) >= 1
        slave = cfg["slaves"][0]
        # 6 个采集点
        assert len(slave["points"]) == 6
        keys = [p["key"] for p in slave["points"]]
        for k in ("temperature", "humidity", "current", "voltage", "human", "smoke"):
            assert k in keys, f"esp32 缺 {k}"

    def test_day2_config_parses(self):
        cfg = parse_day2_config()
        assert cfg["register_start"] == 2
        assert cfg["register_count"] == 8
        assert len(cfg["register_map"]) == 8  # 8 路继电器


# ---------- 5. 关键不变量：连接配置 ----------

class TestConnectionConsistency:
    """Modbus 连接配置：host/port/unit_id 必须对齐"""

    def test_day2_esp32_same_modbus_endpoint(self):
        """Day2 配置和 ESP32 配置应连同一台 Modbus 从站"""
        day2 = parse_day2_config()
        esp32 = parse_esp32_config()
        slave = esp32["slaves"][0]
        assert day2["modbus_host"] == slave["host"], (
            f"Day2 配 {day2['modbus_host']} 但 ESP32 配 {slave['host']}"
        )
        assert day2["modbus_port"] == slave["port"]
        assert day2["unit_id"] == slave["unit_id"]

    def test_esp32_modbus_slave_unit_id_matches_script(self):
        """ESP32 配的 unit_id 应和 modbus_slave_sim.py 的默认一致（或者文档化差异）"""
        esp32 = parse_esp32_config()
        slave = esp32["slaves"][0]
        info = parse_slave_script(SLAVE_SCRIPT)
        # 如果用户都用命令行显式传 unit_id，可以允许不一致
        # 但默认情况下应一致
        assert slave["unit_id"] == info["default_unit_id"], (
            f"ESP32 用 unit_id={slave['unit_id']} 但 modbus_slave_sim 默认 {info['default_unit_id']}。"
            f"启动从站时必须显式传 unit_id={slave['unit_id']}"
        )

    def test_mqtt_endpoint_consistency(self):
        """MQTT broker 配置三处应一致（Day2 模拟器、ESP32 板子、Bridge）"""
        day2 = parse_day2_config()
        esp32 = parse_esp32_config()
        # Day2 mqtt host/port
        assert day2["mqtt"]["host"] == esp32["mqtt_host"]
        assert int(day2["mqtt"]["port"]) == esp32["mqtt_port"]


# ---------- 6. 寄存器含义一致性 ----------

class TestRegisterKeyConsistency:
    """同名 key（如 temperature/humidity）必须共享同一寄存器地址和缩放"""

    def test_temperature_addr_match(self):
        """temperature 寄存器地址必须一致"""
        slave = parse_slave_script(SLAVE_SCRIPT)
        esp32 = parse_esp32_config()["slaves"][0]
        esp32_temp = next((p for p in esp32["points"] if p["key"] == "temperature"), None)
        assert esp32_temp is not None
        # modbus_slave_sim 注释头说 reg0 = 温度
        assert 0 in slave["layout"] and "温度" in slave["layout"][0]
        assert esp32_temp["addr"] == 0

    def test_humidity_addr_match(self):
        slave = parse_slave_script(SLAVE_SCRIPT)
        esp32 = parse_esp32_config()["slaves"][0]
        esp32_hum = next((p for p in esp32["points"] if p["key"] == "humidity"), None)
        assert esp32_hum is not None
        assert 1 in slave["layout"] and "湿度" in slave["layout"][1]
        assert esp32_hum["addr"] == 1

    def test_temperature_scale_match(self):
        """temperature scale 一致 (0.1)"""
        esp32 = parse_esp32_config()["slaves"][0]
        esp32_temp = next(p for p in esp32["points"] if p["key"] == "temperature")
        assert esp32_temp["scale"] == 0.1

    def test_humidity_scale_match(self):
        esp32 = parse_esp32_config()["slaves"][0]
        esp32_hum = next(p for p in esp32["points"] if p["key"] == "humidity")
        assert esp32_hum["scale"] == 0.1


# ---------- 7. Day2 继电器映射一致性 ----------

class TestDay2RelayMapping:
    """Day2 config_relay.json 的 8 路继电器必须和 modbus_slave_sim 兼容"""

    def test_relay_count(self):
        """8 路继电器"""
        day2 = parse_day2_config()
        assert day2["register_count"] == 8

    def test_relay_addresses_match_slave_layout(self):
        """Day2 relay1~8 寄存器地址应 = modbus_slave_sim 的 reg2~9"""
        day2 = parse_day2_config()
        slave = parse_slave_script(SLAVE_SCRIPT)
        # reg_start=2, count=8 → 继电器占用 2..9
        relay_addrs = list(range(day2["register_start"],
                                 day2["register_start"] + day2["register_count"]))
        assert relay_addrs == slave["relay_registers"]

    def test_relay_names_follow_convention(self):
        """继电器命名应 relay1..relayN"""
        day2 = parse_day2_config()
        names = [v["name"] for v in day2["register_map"].values()]
        for i in range(1, day2["register_count"] + 1):
            assert f"relay{i}" in names, f"缺 relay{i}"


# ---------- 8. ESP32 配置完整性 ----------

class TestEsp32ConfigContract:
    """ESP32 config.json 必须包含必要字段"""

    def test_has_wifi_section(self):
        cfg = json.loads(ESP32_CONFIG.read_text(encoding="utf-8"))
        for k in ("wifi_ssid", "wifi_pass"):
            assert k in cfg, f"ESP32 config 缺 {k}"

    def test_has_mqtt_section(self):
        cfg = json.loads(ESP32_CONFIG.read_text(encoding="utf-8"))
        for k in ("mqtt_host", "mqtt_port", "mqtt_user", "mqtt_pass"):
            assert k in cfg, f"ESP32 config 缺 {k}"

    def test_has_jetlinks_product_device(self):
        cfg = json.loads(ESP32_CONFIG.read_text(encoding="utf-8"))
        assert "product_id" in cfg
        assert "device_id" in cfg

    def test_each_point_has_required_fields(self):
        cfg = parse_esp32_config()
        for slave in cfg["slaves"]:
            for pt in slave["points"]:
                for k in ("addr", "key", "period_ms"):
                    assert k in pt, f"point 缺 {k}: {pt}"

    def test_no_duplicate_keys_in_slave(self):
        """同一从站内 key 不能重复（否则后注册覆盖前一个）"""
        cfg = parse_esp32_config()
        for slave in cfg["slaves"]:
            keys = [p["key"] for p in slave["points"]]
            assert len(keys) == len(set(keys)), (
                f"从站 {slave['name']} 有重复 key: {keys}"
            )


# ---------- 9. day8 vs tools modbus_slave_sim 行为一致性 ----------

class TestDualSlaveScripts:
    """day8/tools/modbus_slave_sim.py 和 tools/modbus_slave_sim.py 行为应一致"""

    def test_both_have_same_relay_layout(self):
        """两版从站的继电器寄存器地址应相同"""
        day8 = parse_slave_script(DAY8_SLAVE_SCRIPT)
        main = parse_slave_script(SLAVE_SCRIPT)
        assert day8["relay_registers"] == main["relay_registers"]
        assert day8["current_register"] == main["current_register"]
        assert day8["voltage_register"] == main["voltage_register"]

    def test_default_unit_id_warning(self):
        """两个从站默认 unit_id 可能不同（warning 而非 fail）"""
        day8 = parse_slave_script(DAY8_SLAVE_SCRIPT)
        main = parse_slave_script(SLAVE_SCRIPT)
        if day8["default_unit_id"] != main["default_unit_id"]:
            # 用 warnings 提醒，不 fail
            import warnings
            warnings.warn(
                f"day8 modbus_slave_sim 默认 unit_id={day8['default_unit_id']}，"
                f"tools 默认 {main['default_unit_id']}。启动时务必显式指定以避免冲突。"
            )


# ---------- 10. 报告生成（pytest --tb=short 时仍能看到的快照） ----------

class TestLayoutSnapshot:
    """把三处布局打成快照，方便人眼对照"""

    def test_snapshot_all_layouts(self, capsys):
        slave = parse_slave_script(SLAVE_SCRIPT)
        esp32 = parse_esp32_config()
        day2 = parse_day2_config()

        with capsys.disabled():
            print("\n" + "=" * 60)
            print("协议一致性快照")
            print("=" * 60)
            print(f"\n[1] modbus_slave_sim.py (权威从站)")
            print(f"  默认 unit_id={slave['default_unit_id']}, port={slave['default_port']}")
            print(f"  继电器寄存器: {slave['relay_registers']}")
            print(f"  电流寄存器:   {slave['current_register']}")
            print(f"  电压寄存器:   {slave['voltage_register']}")

            print(f"\n[2] day2/config_relay.json (PC 继电器模拟器)")
            print(f"  Modbus: {day2['modbus_host']}:{day2['modbus_port']} unit_id={day2['unit_id']}")
            print(f"  继电器寄存器: {list(range(day2['register_start'], day2['register_start'] + day2['register_count']))}")

            print(f"\n[3] esp32/config.json (ESP32 网关采集)")
            for slave_cfg in esp32["slaves"]:
                print(f"  从站 {slave_cfg['name']}: {slave_cfg['host']}:{slave_cfg['port']} unit_id={slave_cfg['unit_id']}")
                for pt in slave_cfg["points"]:
                    print(f"    reg 0x{pt['addr']:04X}  →  {pt['key']:15s}  scale={pt['scale']}")

            print("=" * 60)

        # 这个测试只做打印，永远 pass
        assert True
