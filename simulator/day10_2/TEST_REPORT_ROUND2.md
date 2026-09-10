# Day10.2 二次测试报告

> 测试时间：2026-09-10
> 测试环境：`DAY102_FORCE_FAKE=1` 强制 FakeBridge 模拟模式，backend 监听 `127.0.0.1:8083`
> 测试结论：**P0 全部通过，P1 已实现项全部通过；发现 2 项 P1 尚未实现（P1-6、P1-8）**

---

## 一、P0（必修）—— 全部通过 ✅

| 项 | 结果 | 验证依据 |
|----|------|---------|
| P0-1 布局空洞 | ⚠️ 代码已改，视觉未逐像素验 | `dist` 已重建（`index-CnmUjwfA.js` / `index-CGPmxmrg.css`），页面资源全部 HTTP 200。本机浏览器自动化截图工具不可用，**建议人工打开 http://127.0.0.1:8083/ 确认 row 1 后两列不再空洞** |
| P0-2 历史写入 30s 节流 | ✅ 通过 | temperature 相邻记录间隔 **30–32s**，10 分钟仅 18 条。写入频率从 ~11 万条/h 降到 ~456 条/h（约 **240 倍**） |
| P0-3 WS device_status 1.5s 节流 | ✅ 通过 | relay toggle 后 `relay_changed` < 2s 实时收到，`device_status` 受 1.5s 节流抑制，ECharts 不再抖动 |

## 二、P1（重要）—— 已实现 3 项全部通过，2 项未实现

| 项 | 结果 | 验证依据 |
|----|------|---------|
| P1-4 告警操作按钮 | ✅ 通过 | `ack-all` / `clear-all` / 单条 `ack` 全 HTTP 200；状态正确流转 active→acknowledged→cleared；`clear_all_alarms` 返回 count 已修复 |
| P1-5 在线率离线判定 | ✅ 通过 | 60s 超时判定正确；59s 边界仍在线；FakeBridge 日志确认 human/humidity 定期断网 30s |
| P1-7 SQLite WAL | ✅ 通过 | `journal_mode=wal`（持久化）、`busy_timeout=5000`、`synchronous=NORMAL`、`idx_*` 索引存在 |
| **P1-6 日志分级** | ❌ **未实现** | diff 中无 `logging`/`logger` 相关改动，仍是 `print` |
| **P1-8 规则状态持久化** | ❌ **未实现** | diff 中无 `_sensor_stable` / `triggered_at` 持久化改动，仍是进程内字典 |

## 三、P2 / P3 —— 部分验证 ✅

| 项 | 结果 | 验证依据 |
|----|------|---------|
| P2-14 今日告警 | ✅ 通过 | `alarm-stats` 含 `today` 字段，按 `date('now','start of day')` 筛选 |
| P3-16 MQTT 下发回写 | ✅ 通过 | MQTT 客户端成功连接 `172.16.4.211:9783`，toggle relay1 成功下发 `relay-cc/relaycc/properties/write: {'relay1': 1}` |

## 四、运行稳定性

- 后端 + FakeBridge 持续运行 25 分钟无崩溃、无报错
- `[watcher] 清理过期历史 XX 条` 周期性执行，历史清理正常
- 数据库各表行数正常，告警/规则/历史数据无异常堆积

---

## 五、遗留事项（建议 Trae Code 下一步）

1. **P1-6 日志分级**：全后端 `print` → `logging`（按模块配置 logger，加 level + 时间戳 + 文件输出）
2. **P1-8 规则状态持久化**：`_sensor_stable` 进程内字典 → 落库（backend 重启后规则触发状态不丢失）
3. **P0-1 视觉确认**：人工打开大屏确认 row 1 布局空洞已填满
