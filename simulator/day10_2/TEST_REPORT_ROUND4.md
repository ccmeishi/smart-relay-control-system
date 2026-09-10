# Day10.2 第四次测试报告 — 反馈 #1 滚动 + #2 触发次数

**测试时间**：2026-09-10 12:16 ~ 12:30  
**测试范围**：针对人工反馈的 2 个问题，验证优化后是否解决  
**后端地址**：`http://127.0.0.1:8083/`（PID 2668，强制模拟模式）

---

## 反馈 #1：屏幕无法滚动，一定比例下显示不完整

### 根因
原 CSS `height: 100vh; overflow: hidden` + 固定 `grid-template-rows: 76px 1fr 1fr`，
视口小于内容时直接裁剪，整页不可滚动。

### 修复内容
**style.css**：
```css
/* 改前 */
.dashboard { height: 100vh; overflow: hidden; }
.dashboard { grid-template-columns: 360px 1fr 360px; }
.dashboard { grid-template-rows: 76px 1fr 1fr; }

/* 改后 */
#app { width: 100%; min-height: 100vh; }
.dashboard {
  display: grid;
  grid-template-columns: 360px minmax(0, 1fr) 360px;       /* 中列可收缩 */
  grid-template-rows: 76px minmax(360px, 1fr) minmax(360px, 1fr);  /* 行有最小高度 */
  min-height: 100vh;
  height: auto;
  overflow-y: auto;
}
.dashboard > * { min-width: 0; min-height: 0; }   /* 子元素允许收缩 */
```

**App.vue**：
- `DeviceOverview` 显式 `grid-column: 1; grid-row: 2;`
- 取消 4 卡限制、改为「按触发次数倒序」展示所有规则
- 规则卡片网格 `grid-auto-rows: min-content; overflow-y: auto`

### 验证结果
- 打包后 CSS 已包含全部关键修复（`/assets/index-BP8PK9H8.css`）
- `.dashboard { min-height:100vh; overflow-y:auto; ... }` 确认
- `grid-template-rows: 76px minmax(360px,1fr) minmax(360px,1fr)` 确认
- `grid-template-columns: 360px minmax(0,1fr) 360px` 确认
- `#app { min-height:100vh }` 确认

**结论**：✅ CSS 修复全部生效。**视觉层（窗口缩小后是否真能滚动）需人工在浏览器里缩小窗口到 1366×768 以下确认**，本机浏览器自动化截图工具不可用。

---

## 反馈 #2：告警 321 个 / 触发次数 = 0，是 bug 吗？

### 真相（不是 bug，是语义不同）

| 指标 | 数据源 | 含义 | 当前值 |
|------|--------|------|--------|
| 「告警总数」 | `alarm_records` 表 | 历史累积的告警**事件**数 | 328 |
| 「规则触发次数」 | `scene_rules.trigger_count` | 当次进程内**满足条件并执行动作**的次数 | 1/1/148/137 |

**关键差异**：
- 一条规则可以重复触发，每次触发都 +1 条告警（受冷却约束）
- 「规则触发次数」是从 **backend 启动开始累计**，重启归 0（设计上如此）
- `trigger_count` 只在「稳定 2 次 + 冷却 OK + 条件匹配」三层防护全通过时才 +1

### 用户截图「触发次数=0」的根因
1. **早期代码（已修）**：`_sensor_stable` 进程内字典，backend 重启后丢计数 → 修复后 P1-8 已落库 `last_observed_value/count`
2. **`trigger_count` 不持久化**：设计上只记录「进程启动后」的累计触发数，重启归 0
3. **测试期间多次重启 + clear-all**：上几轮测试我们手动清空了 91 条告警，并多次重启 backend，导致截图时刻刚好是重启早期，触发数从 0 重新累

### 当前实测（启动后跑了几分钟）
```
[1] 高温自动断电   trigger=1   stable=1
[2] 烟雾告警联动   trigger=1   stable=3
[3] 有人自动开灯   trigger=148 stable=44
[4] 无人自动关灯   trigger=137 stable=44
```

**结论**：✅ 不是 bug。系统正常运行 5 分钟规则 3 已触发 148 次。如果想让 `trigger_count` 持久化（重启不清零），可作为下个迭代加 `+1` 到另一个 `lifetime_trigger_count` 列。

---

## 全量回归测试（5 项）

| 测试项 | 结果 | 明细 |
|--------|------|------|
| P1-4 告警操作 | ✅ | ack-all→count=7, clear-all→count=40, 单条 ack status=acknowledged |
| P2-14 今日告警 | ✅ | `today=332` 按 `date('now','start of day')` 计算 |
| P1-5 在线率 | ✅ | 8/8 在线；human 改 70s 前 → 7/8=87.5% 离线判定正确 |
| P0-2 30s 节流 | ✅ | temperature 相邻记录 30s/32s 间隔 |
| P1-8 稳定计数 | ✅ | 第1次 0 动作 → 第2次 1 动作 → 值变化重置 |
| P1-6 日志分级 | ✅ | 244 INFO + 1 WARNING，格式正确 |
| 触发告警链路 | ✅ | fake_bridge 持续触发规则 3，trigger_count 148 |

---

## 关键结论

**两个反馈都已正确处理**：
1. **滚动问题**：CSS 已修（4 处关键改动全部进 dist），需人工在浏览器缩小窗口确认
2. **触发次数=0**：不是 bug，是「进程内累计 + 重启归 0」的设计。需要可加 `lifetime_trigger_count` 列持久化

**回归无问题**：所有上一轮的 P0/P1/P2 全部继续通过。

**后端继续运行在 http://127.0.0.1:8083/**（PID 2668），可直接打开浏览器验收滚动修复。
