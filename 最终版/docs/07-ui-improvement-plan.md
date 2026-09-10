# 大屏 UI 改进方案

> 依据老师反馈整理：
> 1. **兼容性**：不同浏览器表现不一致，需统一。
> 2. **布局紧凑性**：大屏展示最好一屏展示完，不要滚动。
> 3. **大屏交互方式**：大屏场景很少用鼠标操作；如果内容多，建议**分标签/分屏切换**，且可**自动轮播，每 10 秒切换一屏**。

---

## 一、问题定位

### 1.1 当前布局为什么会溢出、需要滚动

老师截图里底部被裁切，说明 `.dashboard` 在当前视口里被内容撑高，触发了整页滚动。根本原因是：

```css
.dashboard {
  min-height: 100vh;
  height: auto;            /* 允许随内容增高 */
  grid-template-rows: 76px minmax(360px, 1fr) minmax(360px, 1fr);
}
```

- `height: auto` 让容器被内部内容撑大；
- `minmax(360px, 1fr)` 设定了内容行最小高度 360px，加上头部 76px、gap 14px、padding 14px，**理论最小总高 ≈ 838px**，这还没算每个 `.panel` 自己的 padding 和内部元素；
- 老师使用的浏览器/窗口/缩放下，可视高度不足这个最小值，于是出现整页滚动。

### 1.2 为什么不同浏览器看起来不一样

| 差异来源 | 影响 | 典型表现 |
|---------|------|---------|
| `100vh` 计算方式 | 不同浏览器对工具栏/书签栏/缩放的处理不同 | 同一窗口 Chrome 与 Safari 的有效 `vh` 可能差 20~40px |
| 默认字体回退 | `Orbitron` 未加载，实际使用 Consolas/SFMono/系统字体 | 中文+数字在不同字体下的行高、字重、宽度不同，撑开卡片高度 |
| `backdrop-filter` / `-webkit-background-clip: text` | 旧版 Firefox / 部分浏览器支持度不同 | 可能缺少模糊或渐变文字效果，导致视觉差异 |
| 滚动条宽度 | Windows 默认显示滚动条，macOS 默认 overlay | 出现滚动条时额外占用 17px，进一步压缩内容区 |
| ECharts 仅监听 `window.resize` | 父容器被 grid 重新分配大小时，图表不会自适应 | 某些浏览器初始渲染时机不同，图表可能偏大/偏小 |

---

## 二、总体改进方向

1. **优先采用自动分屏轮播（老师明确建议）**：把当前所有 panel 拆成 2~3 屏，每屏内容较少、无需滚动，自动 10 秒切换。彻底解决“一屏放不下”的问题。
2. **每屏内部紧凑化**：即使分屏后，仍收紧 padding、gap、标题栏、数字大小，保证每屏在 900px 以上高度都能完整显示。
3. **锁定视口，禁止整页滚动**：`.dashboard` 永远等于一屏高（`100vh`），所有滚动都在 panel 内部。
4. **补齐浏览器兼容细节**：font stack、滚动条、ECharts ResizeObserver、backdrop-filter 兜底。

---

## 三、分屏/自动切换方案（老师最新建议）

### 3.1 分屏设计

推荐先做 **2 屏**，结构最简单、信息分组清晰：

| 屏幕 | 名称 | 包含 panel | 信息主题 |
|------|------|-----------|---------|
| 屏 1 | 运行概览 | 设备概览 + 通道状态 + 数据趋势 | 实时运行状态 |
| 屏 2 | 告警与规则 | 告警信息 + 场景联动 + 设备在线率 | 告警、规则、统计 |

后续如需展示更详细的历史趋势，可扩展为 **3 屏**：

| 屏幕 | 名称 | 包含 panel |
|------|------|-----------|
| 屏 1 | 运行概览 | 设备概览 + 通道状态 + 数据趋势 |
| 屏 2 | 告警中心 | 告警信息（全屏放大） |
| 屏 3 | 规则与在线率 | 场景联动 + 设备在线率 |

### 3.2 自动轮播逻辑

在 `DashboardView.vue` 中实现：

- `currentScreen`：当前屏索引（0 / 1）；
- `autoPlay`：是否自动轮播；
- `interval = 10000`：10 秒切换；
- 使用 `setInterval` 或更好的 `setTimeout` 循环（避免累积）。

```vue
<script setup>
import { ref, onMounted, onUnmounted } from 'vue'

const SCREEN_COUNT = 2
const SWITCH_INTERVAL = 10000
const currentScreen = ref(0)
const autoPlay = ref(true)
let timer = null

function nextScreen() {
  currentScreen.value = (currentScreen.value + 1) % SCREEN_COUNT
}

function startAutoPlay() {
  stopAutoPlay()
  timer = setInterval(nextScreen, SWITCH_INTERVAL)
}

function stopAutoPlay() {
  if (timer) { clearInterval(timer); timer = null }
}

onMounted(startAutoPlay)
onUnmounted(stopAutoPlay)
</script>
```

### 3.3 切换时保留数据与图表状态

- 使用 `v-show` 而不是 `v-if` 控制屏幕显隐，保证组件不被销毁、WebSocket 数据持续更新；
- ECharts 实例不会被重建，但需要再切回时触发一次 `resize()`，避免隐藏期间容器尺寸为 0 导致图表空白。

```vue
<template>
  <div class="dashboard">
    <header class="dash-header">...</header>

    <!-- 屏 1 -->
    <div v-show="currentScreen === 0" class="screen screen-1">
      <DeviceOverview />
      <ChannelStatus />
      <DataTrend />
    </div>

    <!-- 屏 2 -->
    <div v-show="currentScreen === 1" class="screen screen-2">
      <AlarmPanel />
      <SceneRules />
      <OnlineRate />
    </div>

    <!-- 屏指示器 -->
    <ScreenIndicator :total="SCREEN_COUNT" :current="currentScreen" :auto-play="autoPlay" />
  </div>
</template>
```

### 3.4 每屏布局建议

**屏 1（运行概览）**：3 列，中间数据趋势占宽，两侧设备概览、通道状态。

```css
.screen-1 {
  grid-column: 1 / 4;
  grid-row: 2 / 4;
  display: grid;
  grid-template-columns: 320px 1fr 320px;
  grid-template-rows: 1fr;
  gap: var(--dash-gap);
  min-height: 0;
}
```

**屏 2（告警与规则）**：3 列，告警信息放大，场景联动 + 在线率堆叠。

```css
.screen-2 {
  grid-column: 1 / 4;
  grid-row: 2 / 4;
  display: grid;
  grid-template-columns: 1fr 340px 340px;
  grid-template-rows: 1fr;
  gap: var(--dash-gap);
  min-height: 0;
}
```

> 如果 2 屏仍觉拥挤，可把告警面板独占一整列（更宽），场景联动与在线率上下堆叠在右侧。

### 3.5 视觉指示器与倒计时

在底部居中增加一行：

- 两个小圆点表示屏 1 / 屏 2，当前屏高亮；
- 一个 10 秒倒计时进度条，直观展示何时切换；
- 显示当前屏名称（如“运行概览 / 告警与规则”）。

```vue
<template>
  <div class="screen-indicator">
    <span class="screen-name">{{ screenNames[currentScreen] }}</span>
    <div class="dots">
      <span
        v-for="(_, i) in SCREEN_COUNT"
        :key="i"
        :class="['dot', { active: i === currentScreen }]"
      />
    </div>
    <div class="progress"><div class="bar" :style="progressStyle" /></div>
  </div>
</template>
```

进度条用 CSS 动画：

```css
.progress {
  width: 120px; height: 2px;
  background: rgba(255,255,255,0.15);
  border-radius: 1px;
  overflow: hidden;
}
.progress .bar {
  height: 100%;
  background: var(--blue);
  animation: progress 10s linear infinite;
}
@keyframes progress { from { width: 0; } to { width: 100%; } }
```

### 3.6 交互控制（可选但建议）

大屏虽少用鼠标，但调试/遥控器/键盘操作需要：

| 按键/操作 | 行为 |
|----------|------|
| 左 / 右方向键 | 手动切换上一屏 / 下一屏，并暂停自动轮播 30 秒 |
| `P` | 暂停 / 恢复自动轮播 |
| 鼠标悬停在指示器 | 暂停自动轮播（方便调试） |
| URL 参数 `?screen=0&autoplay=0` | 指定初始屏、关闭自动轮播 |

### 3.7 切换动画

使用 Vue 的 `<transition>` 或 CSS opacity/translate，避免生硬跳变：

```css
.screen {
  opacity: 0;
  transform: translateX(20px);
  transition: opacity 0.5s ease, transform 0.5s ease;
  pointer-events: none;
}
.screen.active {
  opacity: 1;
  transform: translateX(0);
  pointer-events: auto;
}
```

---

## 四、具体改动清单

### 4.1 `frontend/src/views/DashboardView.vue`

- 引入 `ref/onMounted/onUnmounted`；
- 新增 `currentScreen` / `autoPlay` / `timer` 状态；
- 把现有 6 个 panel 按屏分组；
- 用 `v-show` + `.screen` 容器渲染；
- 新增 `ScreenIndicator` 组件（或内联实现）；
- 监听键盘事件（已有 F/Esc/R，可继续扩展）。

### 4.2 `frontend/src/style.css` —— 大屏根布局与全局样式

**改动要点：**

- `.dashboard` 改为 `height: 100vh; overflow: hidden;`，不再允许整页滚动；
- 收紧 `padding`、`gap`、header 高度；
- 增加 `:root` 的紧凑尺寸 token；
- 全局字体栈增加系统字体兜底，减少浏览器差异；
- 增加 Firefox 滚动条样式；
- 为 `.panel` 增加 `backdrop-filter` 兜底背景。

```css
/* 建议新增/修改 */
:root {
  --dash-padding: 10px;
  --dash-gap: 10px;
  --header-height: 54px;
  --panel-padding: 10px 12px;
  --panel-title-size: 14px;
  --panel-title-margin: 8px;
  --big-num-size: 32px;
}

html, body {
  width: 100%;
  height: 100%;            /* 去掉 min-height:100% + overflow-y:auto */
  overflow: hidden;       /* 禁止 body 滚动 */
}

#app {
  width: 100%;
  height: 100%;
}

body {
  background: #050816;
  color: #e0e6ed;
  font-family: 'PingFang SC', 'Microsoft YaHei', 'Noto Sans SC', 'Helvetica Neue', Arial, sans-serif;
}

/* 等宽数字字体统一 */
.mono {
  font-family: ui-monospace, SFMono-Regular, 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace;
}

.dashboard {
  display: grid;
  grid-template-columns: 1fr;      /* 屏容器独占整行 */
  grid-template-rows: var(--header-height) 1fr;
  gap: var(--dash-gap);
  padding: var(--dash-padding);
  width: 100vw;
  height: 100vh;                    /* 锁定一屏 */
  min-height: 0;
  overflow: hidden;
  position: relative;
  /* 背景保持原样 */
}

.dash-header {
  grid-column: 1 / 2;
  height: var(--header-height);
  padding: 0 16px;
  /* ... */
}

.dash-title {
  font-size: 22px;
  letter-spacing: 2px;
}

.dash-header-right {
  gap: 16px;
  font-size: 14px;
}

.dash-clock {
  font-size: 16px;
}

.panel {
  padding: var(--panel-padding);
  border-radius: 8px;
  /* 兜底背景：blur 不支持时仍可见 */
  background: rgba(16, 28, 56, 0.85);
  background: var(--bg-panel);
  backdrop-filter: blur(8px);
  /* ... */
}

.panel-title {
  font-size: var(--panel-title-size);
  margin-bottom: var(--panel-title-margin);
}

/* 滚动条统一 */
* {
  scrollbar-width: thin;
  scrollbar-color: rgba(64, 158, 255, 0.4) transparent;
}
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-thumb { background: rgba(64, 158, 255, 0.4); border-radius: 3px; }
::-webkit-scrollbar-track { background: transparent; }
```

### 4.3 按高度断点进一步紧凑（加入 `style.css` 末尾）

```css
/* 900px ~ 1080px 之间：适度收紧 */
@media (max-height: 1000px) {
  :root {
    --header-height: 48px;
    --dash-padding: 8px;
    --dash-gap: 8px;
    --panel-padding: 8px 10px;
    --panel-title-margin: 6px;
    --big-num-size: 28px;
  }
  .dash-title { font-size: 20px; }
  .dash-clock { font-size: 14px; }
}

/* 768px ~ 900px：再次收紧，数字更小 */
@media (max-height: 900px) {
  :root {
    --header-height: 44px;
    --dash-padding: 6px;
    --dash-gap: 6px;
    --panel-padding: 6px 8px;
  }
  .dash-title { font-size: 18px; }
  .dash-clock { font-size: 13px; }
}

/* 小于 768px：实在放不下，允许整页滚动 */
@media (max-height: 768px) {
  .dashboard {
    height: auto;
    min-height: 100vh;
    overflow: auto;
  }
}
```

### 4.4 `frontend/src/components/DeviceOverview.vue`

主要减少大数字和卡片内边距：

```css
.total-wrap { padding: 4px 0 8px; }
.total-num { font-size: var(--big-num-size); }

.stat-row { gap: 8px; margin-bottom: 10px; }
.stat-card { padding: 8px; border-radius: 6px; }
.stat-num { font-size: 22px; }

.rate-bar { height: 8px; }
```

### 4.5 `frontend/src/components/ChannelStatus.vue`

减少按钮尺寸、图标、间距：

```css
.relay-grid { gap: 8px; }
.relay-btn { gap: 4px; border-radius: 8px; }
.relay-icon { width: 26px; height: 26px; }
.spinner { width: 26px; height: 26px; }
.relay-name { font-size: 12px; }
.relay-state { font-size: 14px; }
.hint { font-size: 11px; margin-top: 6px; }
```

### 4.6 `frontend/src/components/AlarmPanel.vue`

让告警列表使用面板剩余空间，而不是固定 200px：

```css
.pie { height: 90px; flex-shrink: 0; }      /* 从 130px 缩小 */

.alarm-list {
  flex: 1;
  overflow-y: auto;
  min-height: 0;        /* 关键：允许 flex item 收缩到 0 */
  max-height: none;     /* 去掉固定 200px，交给 flex 分配 */
  border-top: 1px solid rgba(255,255,255,0.06);
  padding-top: 4px;
}

.alarm-stats { margin-bottom: 6px; }
.alarm-stat { padding: 6px 0; border-radius: 6px; }
.num { font-size: 20px; }
.alarm-item { padding: 5px 4px; font-size: 11px; }
```

### 4.7 `frontend/src/components/SceneRules.vue`

减少单条规则卡片高度：

```css
.rule-grid { gap: 6px; padding-right: 2px; }
.rule-card {
  padding: 6px 10px;
  min-height: 52px;      /* 从 78px 降低 */
  border-radius: 6px;
  gap: 2px;
}
.rule-name { font-size: 12px; }
.rule-cond { font-size: 11px; }
.trig-count { font-size: 10px; }
```

### 4.8 `frontend/src/components/DataTrend.vue` & `OnlineRate.vue`

核心问题：**ECharts 只在 `window.resize` 时调用 `chart.resize()`**。当父 panel 被 grid 重新分配大小、或从隐藏（`v-show`）到显示时，图表不会自适应。建议增加 `ResizeObserver`：

```js
import { onMounted, onUnmounted, nextTick } from 'vue'

let ro = null

onMounted(() => {
  // ... 原有 init
  ro = new ResizeObserver(() => {
    nextTick(() => chart && chart.resize())
  })
  ro.observe(chartEl.value)
})

onUnmounted(() => {
  // ... 原有清理
  ro && ro.disconnect()
})
```

注意：`ResizeObserver` 在现代浏览器均支持（Chrome 64+, Edge 79+, Firefox 69+, Safari 13.1+）。如需兼容更旧浏览器，可引入 `element-resize-detector`，但这会引入新依赖；项目要求不引入新依赖，因此直接使用原生 `ResizeObserver`，并在 README 中注明浏览器版本要求即可。

---

## 五、兼容性专项清单

| 项目 | 当前状态 | 建议 |
|------|---------|------|
| `box-sizing` | 已全局设置 | ✅ 保持 |
| `-webkit-background-clip: text` | 已加 | ✅ 保持 |
| `backdrop-filter` | 已用，无兜底 | ⚠️ 加纯色兜底背景 |
| 字体栈 | 只写了 `'Microsoft YaHei', 'PingFang SC', sans-serif` | ⚠️ 增加 macOS/iOS 的 `PingFang SC`、`SF Pro` 及通用 `sans-serif` 兜底 |
| 等宽数字字体 | `Orbitron` 未加载 | ⚠️ 用系统 `ui-monospace/SFMono` 兜底，或改为非等宽但统一字号的普通字体 |
| 滚动条 | 只有 WebKit | ⚠️ 增加 `scrollbar-width/color`（Firefox） |
| 视口单位 | `100vh` | ✅ 桌面大屏足够；如将来投屏到电视/平板，可再考虑 `100dvh` 作为增强（不强制） |
| ECharts resize | 仅 window.resize | ⚠️ 加 ResizeObserver |

---

## 六、推荐实施顺序

**P0（必须做，见效最快）**
1. 在 `DashboardView.vue` 实现**分屏 + 10 秒自动轮播**，用 `v-show` 保留组件状态；
2. 屏内布局改用 3 列，保证单屏无滚动；
3. `style.css` 改为 `height: 100vh; overflow: hidden`，收紧 padding/gap/header；
4. `AlarmPanel.vue` 去掉固定 `max-height: 200px`，改为 flex 自适应。

**P1（显著提升兼容性）**
5. 全局字体栈、等宽数字兜底；
6. `backdrop-filter` 纯色兜底；
7. ECharts 增加 ResizeObserver；
8. 底部屏指示器 + 倒计时进度条。

**P2（锦上添花）**
9. 按 `@media (max-height: 1000px/900px/768px)` 做高度断点；
10. 键盘控制（方向键/P 键暂停）；
11. URL 参数指定初始屏；
12. 在 README / 部署文档里注明推荐浏览器版本。

---

## 七、验证步骤

1. 在 **Chrome / Edge / Firefox** 打开 `http://localhost:8083`（dev 用 `http://localhost:5173`）。
2. 确认页面自动每 10 秒切换一屏，底部进度条走满后切换。
3. 每屏内容都完整可见，无整页滚动条；告警列表、场景规则列表如需滚动，只在 panel 内部滚动。
4. 把窗口高度分别拖到 **1080px、900px、768px**，确认两屏都能完整显示。
5. 用浏览器缩放 **Ctrl + / Ctrl -** 测试 100%、125%、150%，确认无溢出。
6. 测试键盘：方向键切换、P 键暂停/恢复。
7. 老师端如果仍有问题，请老师按 `F12 → Console → 输入 window.innerHeight 回车`，把高度和浏览器型号发回，方便精确调整断点。

---

## 八、是否引入新依赖

**不引入新依赖**。分屏、轮播、动画均用 Vue3 原生能力 + CSS；自适应用原生 `ResizeObserver`；字体用系统字体栈。

---

## 九、给老师反馈的要点

- 之前出现差异，是因为 6 个 panel 全挤在一屏，最小高度已超过许多浏览器/窗口的有效可视高度，导致滚动和裁切；
- 已按老师建议改为**自动分屏轮播**：屏 1 运行概览（设备 + 通道 + 趋势），屏 2 告警与规则（告警 + 场景 + 在线率），每 10 秒自动切换，无需鼠标操作；
- 同时保留紧凑化与浏览器兼容优化（字体栈、backdrop 兜底、ECharts 自适应），保证每屏内部在不同浏览器下一致；
- 如需更细粒度，可扩展为 3 屏（告警单独一屏），或让老师提供具体浏览器和 `window.innerHeight` 进一步精确。
