# 02 - 架构设计

## 一、全链路数据流

```
ESP32-C3 网关 (product_id=relay-cc, device_id=relaycc)
   │  Modbus TCP 读温/湿/人/烟 (从站 192.168.20.59:5502, unit_id=7)
   │  4 路 GPIO 继电器 (IO 3,4,5,7 高电平触发)
   ▼  MQTT 上报 (8 个 key 混在一条 payload)
Bridge (backend/bridge/gateway_bridge.py) —— 独立子进程
   │  ① 按路由表拆分转发到 8 个虚拟设备
   │  ② 评估场景规则 → 命中则 MQTT 下发继电器 + 写告警
   ▼  写 SQLite (WAL 模式, 8 张表)
Flask (backend/app.py) —— DataWatcher 后台线程 0.5s 扫库
   │  检测 device_status 变化 → 写历史(30s 节流) → 广播 WS(1.5s 节流)
   ▼
ws://localhost:8083/ws/dashboard → Vue3 大屏 (6 模块, 免登录)
                                → 管理后台 (7 页面, 需登录)
```

## 二、进程与数据边界

系统由两个独立进程组成，通过 SQLite 解耦：

| 进程 | 职责 | 不能做 |
|------|------|--------|
| Bridge 子进程 | 订阅 MQTT、拆分转发、规则引擎、写库 | 不能直接调用 Flask 的 WebSocket |
| Flask 主进程 | REST/WS 服务、DataWatcher 轮询、鉴权 | 不直接连 MQTT（仅 toggle 时下发） |

**为何解耦**：Bridge 子进程崩溃重启不影响 Web 服务；Flask 重载不丢采集数据；SQLite WAL 支持两进程并发读写。

## 三、关键设计决策

### 1. 数据源自动选择（bridge_runner.choose_and_start）

优先级：
1. `DAY102_FORCE_FAKE=1` → 强制 FakeBridge（演示/无硬件）
2. MQTT broker TCP 可达 → 真实 `gateway_bridge.py`
3. MQTT 不可达 → 回退 FakeBridge（大屏不空白）

子进程崩溃 5 秒后自动重启（`BridgeRunner.watch`）。

### 2. WebSocket 推送节流

DataWatcher 后台线程轮询 SQLite，避免高频广播：

| 事件 | 触发 | 节流 |
|------|------|------|
| device_status | 状态变化 | 1.5s 最小间隔 |
| history_tick / overview_tick | 定时 | 每 5s |
| alarm_new | 新告警 id | 即时 |
| rule_triggered | trigger_count 增长 | 即时 |
| relay_changed | 大屏点击 toggle | 即时 |

### 3. 在线率计算（db.get_overview）

```
online = device_status 中 updated_at >= now - 60s 的通道数
online_rate = online / 8 * 100%
```

无独立在线表，复用 `device_status.updated_at`。60s 阈值让断网立即反映到大屏（原 5 分钟太长不便演示）。

### 4. 场景规则四层防护（db.evaluate_scene_rules）

1. **稳定计数**：连续 2 次相同值才触发（`STABLE_THRESHOLD=2`，持久化到 `scene_rules.last_observed_count`，跨进程/重启不丢）
2. **冷却时间**：`cooldown_sec` 内不重复触发
3. **条件评估**：`operator + threshold` 匹配
4. **动作互斥锁**：critical（全关）锁定 info（开灯）动作

### 5. 鉴权：Flask 服务端 Session

- 大屏相关接口免登录
- 管理接口需 `login_required`，写操作需 `admin_required`
- 同一用户新登录踢掉旧会话（`kick_user_sessions`）
- `before_request` 心跳更新 `last_seen`，5 分钟无心跳判离线

### 6. 前端 SPA 由 Flask 托管

不使用 Flask 内置 `static_folder`（会拦截子路由导致 SPA fallback 失效），改用 `index()` + `spa()` 手工托管，支持 `history` 模式刷新。

## 四、表结构概览（8 张表）

| 表 | 用途 |
|----|------|
| device_mappings | gateway_key → 虚拟产品/设备/属性 路由 |
| device_status | 设备最新值缓存（在线判定依据） |
| device_status_history | 时序历史（折线图，30s 节流，60 分钟清理） |
| scene_rules | 联动规则 + 稳定计数 + 触发计数 |
| alarm_records | 告警三态流转 |
| dashboard_config | 大屏运行参数 |
| users | 账号 + 角色（admin/user） |
| login_sessions | 在线/离线 + 心跳 |

相关文档：[00-项目概述](00-overview.md) ｜ [04-API文档](04-api.md) ｜ [03-演进历史](03-evolution.md)
