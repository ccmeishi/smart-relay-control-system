# 01 - 快速开始

## 环境要求

| 依赖 | 最低版本 | 说明 |
|------|----------|------|
| Python | 3.10+ | 测试环境 3.12 |
| Node.js | 18+ | 仅首次构建前端 dist/ 需要 |
| pip | 最新 | 自动安装 backend/requirements.txt |
| 操作系统 | Windows 10+ | start_all.bat / stop_all.bat 为 Windows 批处理 |

> **前端 dist 已随仓库提交**，如果不做前端开发，无需安装 Node.js。

---

## 模式一：模拟器模式（推荐，5 步走）

**无硬件、无 MQTT broker，一键跑完整链路演示。**

### Step 1：双击 start_all.bat

双击 `最终版/start_all.bat`，菜单出现：

```
============================================================
  Smart Relay Control System - Integrated Edition
============================================================

  [1] Start - Simulator Mode  - recommended, no hardware
  [2] Start - Hardware Mode   - needs ESP32 + MQTT broker
  [3] Start - Dev Mode        - frontend hot reload on :5173
  [4] Start - Backend Only   - no browser auto-open
  [5] Run Tests               - pytest
  [6] Clean Database          - delete iot_platform.db
  [7] Exit

Select:
```

### Step 2：输入 `1` 回车

start_all.bat 设置 `DAY102_FORCE_FAKE=1`，进入模拟器模式。

### Step 3：等待自动预检（约 15-30 秒）

脚本依次执行 4 项检查：

1. **Python 检测** — `python --version`
2. **后端依赖** — 检测 flask / flask-sock / paho-mqtt，缺失则 `pip install -r backend\requirements.txt`
3. **端口 8083** — netstat 检测 LISTENING，占用则提示是否继续
4. **前端构建** — 检查 `frontend\dist\index.html` 是否存在，缺失则自动 `npm install && npm run build`

### Step 4：后端启动，FakeBridge 自动运行

Flask 后端启动在 port 8083，bridge_runner 检测到 DAY102_FORCE_FAKE=1 后启动 `backend/bridge/fake_bridge.py` 子进程。

FakeBridge 每 2 秒写一批模拟数据（温湿度漂移、人体感应翻转、烟雾随机游走），并自行评估 4 条场景规则，驱动大屏联动和告警。

### Step 5：浏览器自动打开 http://localhost:8083

大约 8 秒后浏览器弹出。大屏将显示：

- **设备概览**：8 个虚拟设备（4 继电器 + 4 传感器），FakeBridge 刚启动时可能还没写满 8 条 device_status，等几秒 online 计数会上升
- **实时通道**：温度 / 湿度 / 人体 / 烟雾持续漂移
- **告警面板**：等约 120 秒 FakeBridge 触发首次异常冲高，即可看到 critical 级告警
- **继电器控制**：点击继电器卡片可切换 ON/OFF（模拟器模式下直接写库，MQTT 下发降级）

### 停止

关闭后端 cmd 窗口，或运行：

```
双击 stop_all.bat
```

stop_all.bat 用 `taskkill /pid <PID> /T /F` 杀整个进程树（Flask + fake_bridge 子进程），然后用 wmic 兜底清理孤儿 bridge 进程。

---

## 模式二：实物模式（需硬件）

### 硬件清单

| 组件 | 说明 |
|------|------|
| ESP32-C3 四路继电器开发板 | 刷 MicroPython v1.29.0 固件 |
| Modbus TCP 从站模拟器 | `tools/modbus_slave_sim.py`，端口 5502，unit_id=7 |
| EMQX broker | 默认 172.16.4.211:9783 |

### Step 1：配置 firmware/config.json

ESP32 固件配置文件，关键字段：

```json
{
  "mqtt_host": "172.16.4.211",
  "mqtt_port": 9783,
  "mqtt_user": "test",
  "mqtt_pass": "123456",
  "product_id": "relay-cc",
  "device_id": "relaycc",
  "modbus_slaves": [
    {
      "host": "192.168.20.59",
      "port": 5502,
      "unit_id": 7,
      "points": [
        {"addr": 0, "key": "temperature", "scale": 0.1},
        {"addr": 1, "key": "humidity",    "scale": 0.1},
        {"addr": 4, "key": "human",       "scale": 1},
        {"addr": 5, "key": "smoke",       "scale": 1}
      ]
    }
  ]
}
```

> Bridge 也会读取这个 config.json（`db.GATEWAY_CONFIG_PATH`），确保 MQTT 凭据一致。

### Step 2：启动 Modbus 从站模拟器

```
python tools/modbus_slave_sim.py
```

### Step 3：刷写 ESP32 固件

```
esptool --chip esp32c3 write_flash 0x0 firmware/_firmware/ESP32_GENERIC_C3-v1.29.0.bin
```

或使用 Thonny 直接拷贝 `firmware/*.py` + `firmware/config.json` 到板子。

### Step 4：双击 start_all.bat → 输入 `2`（Hardware Mode）

脚本设置 `DAY102_FORCE_FAKE=0`，bridge_runner 会 TCP 探测 MQTT broker（`mqtt_reachable()` 用 2 秒超时）：

- **可达** → 启动 `backend/bridge/gateway_bridge.py`（真实 ESP32 数据）
- **不可达** → 自动回退到 FakeBridge（保证大屏不空白）

### Step 5：浏览器打开 http://localhost:8083

继电器控制会通过 MQTT topic `relay-cc/relaycc/properties/write` 下发到 ESP32。

---

## 模式三：开发模式（前端热重载）

```
双击 start_all.bat → 输入 3
```

额外启动：

```
http://localhost:5173
```

后端仍在 8083，Vite dev server 托管前端，保存 .vue 文件浏览器自动刷新。

手动启动命令：

```powershell
# 后端
cd backend && set DAY102_FORCE_FAKE=1 && python app.py

# 前端（另一窗口）
cd frontend && npm run dev
```

Vite dev server 会代理 `/api` 和 `/ws` 到 8083。

---

## 仅后端模式

```
双击 start_all.bat → 输入 4
```

启动 Flask + FakeBridge 但不开浏览器。适合已在浏览器中访问 8083 的场景。

---

## 测试命令

### 运行全部 pytest

```powershell
# 方式 1: start_all.bat 菜单 → 5
# 方式 2: 命令行
cd 最终版
pip install -r requirements-dev.txt
pytest tests/ -v --tb=short
```

测试覆盖：

| 测试文件 | 目标 |
|----------|------|
| `test_esp32_modbus_gw.py` | ESP32 Modbus 主站逻辑 |
| `test_gateway_bridge.py` | Bridge 路由转换 |
| `test_modbus_slave_sim.py` | Modbus 从站模拟器 |
| `test_mqtt_integration.py` | MQTT 报文格式 |
| `test_protocol_consistency.py` | 协议一致性 |
| `test_sensor_simulator.py` | 传感器模拟器 |
| `e2e/test_e2e_full_chain.py` | 8 步端到端 |

预期结果：**166 passed, 1 xfailed**（xfailed 是已知不可测场景）

### 运行 e2e 单独测试

```powershell
cd 最终版
pytest tests/e2e/ -v --tb=short
```

e2e conftest.py 会：
1. 随机分配一个空闲端口
2. 设置 `DAY102_FORCE_FAKE=1` 启动后端子进程
3. 等 30 秒内 `/api/overview` 返回 200 判定就绪
4. 等 FakeBridge 写满 3 秒数据
5. teardown 时用 `taskkill /pid <PID> /T /F` 杀整个进程树，再 sweep 孤儿 fake_bridge / gateway_bridge 进程

---

## 数据库管理

### 查看/管理

```powershell
python -c "import db; db.init_db(); print(db.list_scene_rules()); print(db.list_users())"
```

或运行 db.py 自测：

```powershell
cd 最终版
python -m backend.db
python -m backend.db --force   # 强制删库重建
```

### 清理数据库

```
双击 start_all.bat → 6
```

脚本会先停后端（netstat + taskkill /T），然后删 iot_platform.db / iot_platform.db-wal / iot_platform.db-shm。

---

## 常见启动坑

### 1. bat 双击后闪退 / "不是内部或外部命令"

**根因**：Windows batch 文件对编码和括号非常敏感。start_all.bat 已严格满足：

- 必须是 **CRLF 换行**（LF 会导致 `goto` 失败）
- 文件内所有文字 **纯 ASCII + chcp 65001 切换**（中文菜单已经 chcp 65001）
- `if` 块 **不用括号**（改用 `goto` 标签跳转）

如果改 bat 后闪退，先检查编码：用记事本保存为 **ANSI 或 UTF-8 with BOM**，换行符选 CRLF。

### 2. Python / pip 找不到

```
[ERROR] Python not found. Install Python 3.10+ and add to PATH.
```

安装 Python 时勾选 "Add Python to PATH"。命令行验证：

```powershell
python --version
pip --version
```

### 3. 端口 8083 被占用

```
[WARN] Port 8083 is already in use. Backend may already be running.
```

要么 `stop_all.bat` 停掉旧进程，要么手动：

```powershell
netstat -ano | findstr ":8083 " | findstr "LISTENING"
taskkill /pid <PID> /f /t
```

### 4. 前端未构建

start_all.bat 自动处理。如果手动跳过了 dist 构建：

```powershell
cd frontend
npm install
npm run build
# 构建产物在 frontend/dist/，Flask 会托管
```

### 5. pip 安装报错 pymodbus

requirements-dev.txt 锁定了 `pymodbus==3.6.9`。如果 `pip install -r requirements-dev.txt` 报找不到版本：

```powershell
pip install pymodbus==3.6.9 --index-url https://pypi.org/simple/
```

**不要升级到 3.15.x** — 改了 `ModbusTcpClient` 构造函数签名，测试会挂。

### 6. SQLite "database is locked"

常见于 bridge 子进程未正常退出（孤儿进程持 WAL 锁）。执行：

```
stop_all.bat
```

stop_all.bat 的 `/T` 参数会杀掉整个进程树（包括子进程），然后 wmic 兜底扫孤儿 bridge。e2e 的 teardown 用的是同样策略。

### 7. 大屏在线率 0/8

等 3-5 秒，让 FakeBridge 写满 8 条 device_status。如果长时间保持 0/8：

```powershell
# 查后端日志
type logs\fake_bridge.log
# 查数据库是否有数据
python -c "import db; print(db.get_device_status_all())"
```

---

## 下一步

- 理解全链路设计 → [02-架构设计](02-architecture.md)
- 查 API 用法 → [04-API 手册](04-api.md)
- 生产部署 → [05-部署指南](05-deploy.md)
