<template>
  <div class="dashboard">
    <!-- 头部 -->
    <header class="dash-header">
      <div class="dash-title">智慧物联网平台 · 实时监控大屏</div>
      <div class="dash-header-right">
        <span class="ws-dot" :class="{ online: store.wsConnected }">
          {{ store.wsConnected ? '实时连接' : '断线重连中' }}
        </span>
        <span class="dash-clock">{{ clock }}</span>
      </div>
    </header>

    <!-- 屏 1: 运行概览 -->
    <div v-show="currentScreen === 0" class="screen screen-1">
      <DeviceOverview class="cell" />
      <ChannelStatus class="cell" />
      <DataTrend class="cell" />
    </div>

    <!-- 屏 2: 告警与规则 -->
    <div v-show="currentScreen === 1" class="screen screen-2">
      <AlarmPanel class="cell alarm-main" />
      <SceneRules class="cell" />
      <OnlineRate class="cell" />
    </div>

    <!-- 底部屏指示器 -->
    <div class="screen-indicator">
      <span class="screen-name">{{ screenNames[currentScreen] }}</span>
      <div class="dots">
        <span
          v-for="(_, i) in SCREEN_COUNT"
          :key="i"
          :class="['dot', { active: i === currentScreen }]"
        />
      </div>
      <div class="progress" v-if="autoPlay">
        <div class="bar" :style="progressStyle" />
      </div>
      <span class="auto-hint" v-if="!autoPlay">已暂停 (P键恢复)</span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useDashboardStore } from '../stores/dashboard'
import { WsClient } from '../api/ws'
import DeviceOverview from '../components/DeviceOverview.vue'
import ChannelStatus from '../components/ChannelStatus.vue'
import AlarmPanel from '../components/AlarmPanel.vue'
import DataTrend from '../components/DataTrend.vue'
import SceneRules from '../components/SceneRules.vue'
import OnlineRate from '../components/OnlineRate.vue'

const store = useDashboardStore()
const clock = ref('')

// ---- 自动分屏轮播 ----
const SCREEN_COUNT = 2
const SWITCH_INTERVAL = 10000
const screenNames = ['运行概览', '告警与规则']
const currentScreen = ref(0)
const autoPlay = ref(true)
let autoTimer = null
let progressTimer = null
const progressPct = ref(0)

const progressStyle = computed(() => ({ width: `${progressPct.value}%` }))

function nextScreen() {
  currentScreen.value = (currentScreen.value + 1) % SCREEN_COUNT
}

function startAutoPlay() {
  stopAutoPlay()
  autoTimer = setInterval(nextScreen, SWITCH_INTERVAL)
  // 进度条: 每 50ms 走 1/200
  progressPct.value = 0
  progressTimer = setInterval(() => {
    progressPct.value += 0.5
    if (progressPct.value >= 100) progressPct.value = 0
  }, 50)
}

function stopAutoPlay() {
  if (autoTimer) { clearInterval(autoTimer); autoTimer = null }
  if (progressTimer) { clearInterval(progressTimer); progressTimer = null }
}

// 切屏后触发所有 ECharts resize (v-show 下图表尺寸可能为 0)
watch(currentScreen, () => {
  nextTick(() => {
    window.dispatchEvent(new Event('resize'))
  })
})

// ---- 时钟 ----
let clockTimer = null
let pollTimer = null
let wsClient = null

function updateClock() {
  const d = new Date()
  const p = (n, len = 2) => String(n).padStart(len, '0')
  clock.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
                `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())} 北京时间`
}

onMounted(async () => {
  updateClock()
  clockTimer = setInterval(updateClock, 1000)

  await store.initLoad()

  wsClient = new WsClient(
    (ev) => store.applyEvent(ev),
    (online) => { store.wsConnected = online }
  )
  wsClient.connect()

  pollTimer = setInterval(() => {
    store.pollOverview()
    store.pollAlarmStats()
    store.pollSceneRules()
  }, 5000)

  // 分屏自动轮播
  startAutoPlay()

  // 键盘快捷键
  document.addEventListener('keydown', onKeydown)
})

function onKeydown(e) {
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA') return
  switch (e.key.toLowerCase()) {
    case 'f':
      if (!document.fullscreenElement) document.documentElement.requestFullscreen()
      else document.exitFullscreen()
      break
    case 'escape':
      if (document.fullscreenElement) document.exitFullscreen()
      break
    case 'r':
      if (wsClient) { wsClient.close(); wsClient.connect() }
      break
    case 'p':
      autoPlay.value = !autoPlay.value
      if (autoPlay.value) startAutoPlay()
      else stopAutoPlay()
      break
    case 'arrowleft':
      currentScreen.value = (currentScreen.value - 1 + SCREEN_COUNT) % SCREEN_COUNT
      if (autoPlay.value) startAutoPlay()
      break
    case 'arrowright':
      currentScreen.value = (currentScreen.value + 1) % SCREEN_COUNT
      if (autoPlay.value) startAutoPlay()
      break
  }
}

onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(pollTimer)
  stopAutoPlay()
  document.removeEventListener('keydown', onKeydown)
  wsClient && wsClient.close()
})
</script>

<style scoped>
.cell {
  min-height: 0;
  min-width: 0;
}

/* 屏 1: 运行概览 — 3 列 (设备概览 / 通道状态 / 数据趋势) */
.screen-1 {
  grid-column: 1 / 4;
  grid-row: 2 / 4;
  display: grid;
  grid-template-columns: 1fr 1fr 2fr;
  grid-template-rows: 1fr;
  gap: 10px;
  min-height: 0;
}
.screen-1 .cell:nth-child(1) { grid-column: 1; }  /* DeviceOverview */
.screen-1 .cell:nth-child(2) { grid-column: 2; }  /* ChannelStatus */
.screen-1 .cell:nth-child(3) { grid-column: 3; }  /* DataTrend (跨高) */

/* 屏 2: 告警与规则 — 告警放大占左大列, 场景+在线率占右 */
.screen-2 {
  grid-column: 1 / 4;
  grid-row: 2 / 4;
  display: grid;
  grid-template-columns: 2fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 10px;
  min-height: 0;
}
.screen-2 .alarm-main { grid-column: 1; grid-row: 1 / 3; }
.screen-2 .cell:nth-child(2) { grid-column: 2; grid-row: 1; }  /* SceneRules */
.screen-2 .cell:nth-child(3) { grid-column: 2; grid-row: 2; }  /* OnlineRate */

/* 屏指示器 */
.screen-indicator {
  grid-column: 1 / 4;
  grid-row: 4;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  padding: 4px 0;
  font-size: 12px;
  color: var(--text-dim);
}
.screen-indicator .dots {
  display: flex;
  gap: 6px;
}
.screen-indicator .dot {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: rgba(255,255,255,0.2);
  transition: all 0.3s;
}
.screen-indicator .dot.active {
  background: var(--blue);
  box-shadow: 0 0 6px var(--blue);
  width: 20px;
  border-radius: 4px;
}
.screen-indicator .progress {
  width: 120px; height: 2px;
  background: rgba(255,255,255,0.15);
  border-radius: 1px;
  overflow: hidden;
}
.screen-indicator .progress .bar {
  height: 100%;
  background: var(--blue);
  transition: width 0.05s linear;
}
.screen-indicator .auto-hint {
  color: var(--orange);
}
</style>
