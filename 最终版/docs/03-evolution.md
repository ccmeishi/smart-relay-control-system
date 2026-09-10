# 03 - 演进历史

本项目由 day1 ~ day10.2 共 8 个开发阶段逐步迭代整合而来。每个阶段解决一个核心问题，最终收敛为单一可运行项目。原各阶段代码完整保留在 `simulator/` 目录，方便查阅演进过程。

## 阶段总览

| 阶段 | 主题 | 核心产出 |
|------|------|----------|
| Day1 | PC 模拟器 + Modbus 从站 | 纯 Python 模拟继电器与传感器 |
| Day2 | JetLinks 协议对接 | MQTT 物模型上报 + properties/write 下发 |
| Day5 | ESP32 固件 | 继电器 GPIO + AP 配网 |
| Day7 | Modbus 采集 | 时间片轮询温/湿/人/烟 |
| Day8 | Bridge 网关 | 一块板子拆分为多虚拟设备 |
| Day9 | Web 管理后台 | SQLite 动态路由 + Flask + 权限 |
| Day10 | 场景联动 + 告警 | 规则引擎 + 告警三态 |
| Day10.2 | Vue3 实时大屏 | WebSocket 推送 + 异常冲高演示 |

## Day1 — PC 模拟器

无硬件起步，用 Python 模拟继电器开关与 Modbus 从站响应，验证 Modbus TCP 主从交互与数据格式。产出 `tools/modbus_slave_sim.py`。

## Day2 — JetLinks 协议对接

接入 JetLinks 平台，定义 MQTT 物模型（relay1~4 / temperature / humidity / human / smoke），按 `properties/report` 上报、`properties/write` 下发。确立 product_id/device_id 命名规范。

## Day5 — ESP32 固件

刷 MicroPython 到 ESP32-C3，实现：
- `relay_hw.py`：GPIO 3/4/5/7 高电平触发四路继电器
- `ap_config.py`：首次上电开热点 `RELAY-SETUP-xxxx`，手机连 `192.168.4.1` 配 WiFi + MQTT
- `app_config.py`：`config.json` 作为唯一可信配置源
- `boot.py` / `main.py`：开机入口

## Day7 — Modbus 采集

`modbus_gw.py` 作为 Modbus TCP 主站，时间片轮询从站 `192.168.20.59:5502`（unit_id=7），读取温度（addr 0）、湿度（addr 1）、人体（addr 4）、烟雾（addr 5），按各自 `period_ms` 独立采集。

## Day8 — Bridge 网关

关键重构：ESP32 只连 1 个网关产品（`relay-cc/relaycc`），所有 8 个 key 混在一条 MQTT payload 上报，Python Bridge 订阅后按路由表拆分转发到 8 个虚拟设备。从此一块板子对外呈现为八个设备。

**挑战**：为何不每个 key 单独 MQTT 上报？——JetLinks 平台按产品/设备计费，8 个 key 单独上报需要 8 个网关产品 + 设备配额，实训环境资源有限。混一条 payload + Bridge 拆分是"一块板子多设备"的折中方案。

## Day9 — Web 管理后台 + 鉴权

- SQLite（WAL）替代硬编码路由：`device_mappings` 表，Web 可增删改
- Flask + flask-sock，REST 接口 + WebSocket
- Session 鉴权：`users`（admin/user 角色）、`login_sessions`（在线/离线心跳、踢旧会话）
- 设备控制台、映射管理、用户管理、在线会话页

**挑战**：为何 SQLite 而不是 PostgreSQL？——教学项目零运维启动；但需解决 Bridge/Flask 双进程并发写的"database is locked"。最终配置 WAL + `busy_timeout=5000` + `synchronous=NORMAL`，锁冲突率从 15% 降到 <0.1%。

## Day10 — 场景联动 + 告警

新增两张表：
- `scene_rules`：IF 采集点满足条件 THEN 执行动作，含冷却时间、稳定计数、触发计数
- `alarm_records`：active → acknowledged → cleared 三态

默认 4 条规则：高温 >35 全关（critical 60s）、烟雾 >50 全关（critical 30s）、有人=1 开灯（info 10s）、无人=0 关灯（info 10s）。

**挑战**：为何四层防护？——早期只用简单 `if value > 35 then trigger`，结果温度在 34.9~35.1 抖动时每秒触发一次全关继电器。四层防护：① 稳定计数（连续 2 次相同值）② 冷却时间（60s 不再触发）③ 条件评估 ④ 动作互斥锁（critical 锁定 info），彻底解决抖动问题。

## Day10.2 — Vue3 实时大屏 + WebSocket

- Vue3 + Vite + Pinia + ECharts 深色科技风大屏，6 个模块（DeviceOverview/ChannelStatus/AlarmPanel/DataTrend/SceneRules/OnlineRate）
- WebSocket 实时推送，免登录访问
- `device_status_history` 表存时序数据（30s 节流、60 分钟清理）
- FakeBridge 增强：每约 120s 触发温度冲高 37 或烟雾冲高 62（持续 20s），并随机让某传感器断网 75s（>60s 在线阈值），用于演示 critical 联动与离线场景
- 稳定计数持久化到 SQLite（`last_observed_value/count`），解决 Bridge 重启后首次评估被跳过的问题

**两个关键决策**：
1. **在线阈值 60s 而非 5 分钟**：原设计 5 分钟，教学演示等太久；改成 60s 后 FakeBridge 断网 75s 可立即看到离线效果
2. **告警硬上限 5 条 + CSS max-height:200px**：早期只设 20 条上限 + flex:1 容器，FakeBridge 每秒触发提示级规则时告警面板越拉越长，把场景联动挤没。改为硬上限 5 条 + max-height 固定高度，新告警顶入旧告警滑出

## 整合

最终将 8 个阶段合并为 `最终版/` 单一目录：`backend/` + `frontend/` + `firmware/` + `tools/` + `tests/`，配 `start_all.bat` 一键启动，e2e 全链路 8 步测试全通过。

相关文档：[00-项目概述](00-overview.md) ｜ [02-架构设计](02-architecture.md)
