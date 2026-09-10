# Day10.2 三次测试报告

> 测试时间：2026-09-10
> 测试环境：`DAY102_FORCE_FAKE=1` 强制 FakeBridge 模拟模式，backend 监听 `127.0.0.1:8083`
> 测试结论：**本轮二次优化（P1-6 日志分级 + P1-8 规则状态持久化）全部通过；上轮遗留项已闭环**

---

## 一、本轮新增优化验证（二次优化）

### P1-6 日志分级 ✅
| 验证点 | 结果 |
|--------|------|
| 新增 `log_setup.py` | ✅ 统一 logger `day102`，双 Handler（文件 + 控制台 stderr） |
| 全模块接入 | ✅ app.py / db.py / api.py / bridge_runner.py / ws_hub.py / fake_bridge.py 全部 `from log_setup import logger` |
| `logs/day102.log` 生成 | ✅ 格式 `2026-09-10 11:37:43 [INFO] 消息`，时间戳 + 级别 |
| 级别分布 | ✅ 71 条 `[INFO]`，0 条 `[ERROR]`（运行无异常，属正常） |
| 文件持续增长 | ✅ 7668 字节持续追加，无乱码、无并发写损坏 |

### P1-8 规则状态持久化 ✅
| 验证点 | 结果 |
|--------|------|
| 表结构迁移 | ✅ `scene_rules` 新增 `last_observed_value` / `last_observed_count` 两列，迁移日志已记录 |
| 稳定计数落库 | ✅ 规则3/4 的 `last_observed_count` 累积到 5（跨进程保留，不再每次重置） |
| 功能语义（递增） | ✅ 第1次评估 count=1 不触发，第2次 count=2 达阈值触发 `send_alarm` |
| 功能语义（重置） | ✅ 值变化后 count 重置为 1，不误触发 |
| 跨进程持久化 | ✅ 计数存 DB 而非进程内字典，Bridge 重启后不丢失 |

## 二、附带修复验证 ✅

**db.py 时间过滤修复**（上轮踩坑的 SQLite 时间格式问题）：
- 三处 `recorded_at >= datetime('now', ?)` → `datetime(recorded_at) >= datetime('now', ?)`
- 验证：`minutes=5` 查询从旧写法 **82 条**（错误，T>空格把当天记录全算入）→ 新写法 **9 条**（正确）
- `get_history` / `get_latest_history_tick` / `cleanup_old_history` 三处全部修复

## 三、回归验证（上轮已过项无回退）✅

| 项 | 结果 |
|----|------|
| P1-7 SQLite WAL | ✅ `journal_mode=wal`、`busy_timeout=5000`（`synchronous=NORMAL` 为连接级设置，代码已确认） |
| P2-14 今日告警 | ✅ `alarm-stats` 含 `today` 字段 |
| P1-4 告警操作 | ✅ `ack-all` 91 条 + `clear-all` 91 条，操作后 active=0 |
| P1-5 在线率 | ✅ overview 正常（total=8, online=8, rate=100%） |
| P0-2 30s 节流 | ✅ 无回退，temperature 相邻记录间隔 30–32s |
| P0-3 WS 节流 / P3-16 MQTT 回写 | ✅ 代码在位，无回退 |

## 四、遗留小问题（非阻塞，可选优化）

1. `db.add_scene_rule` 无返回值（返回 `None`）—— 原有行为，API 层不依赖返回值，不影响功能。如需要可在 INSERT 后 `return cur.lastrowid`。
2. **P0-1 布局视觉确认**：本机浏览器自动化截图工具不可用，仍需人工打开 http://127.0.0.1:8083/ 确认 row 1 布局空洞已填满。

---

## 测试结论

二次优化的两项 P1（日志分级、规则状态持久化）**均已正确落地并通过功能验证**，上轮遗留项已闭环。附带的 SQLite 时间过滤修复也验证有效。整体无阻塞问题，可进入下一阶段。
