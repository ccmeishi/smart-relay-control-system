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

    <!-- 左列: 设备概览(row 2) + 通道状态(row 3) -->
    <DeviceOverview class="cell" style="grid-column: 1; grid-row: 2;" />
    <ChannelStatus class="cell" style="grid-column: 1; grid-row: 3;" />

    <!-- 中列: 数据趋势(跨 row 2-3) -->
    <DataTrend class="cell" style="grid-column: 2; grid-row: 2 / 4;" />

    <!-- 右列: 告警面板(row 2) + 场景规则/在线率(row 3) -->
    <AlarmPanel class="cell" style="grid-column: 3; grid-row: 2;" />
    <div class="cell" style="grid-column: 3; grid-row: 3; display: grid; grid-template-rows: 1fr 1fr; gap: 14px;">
      <SceneRules />
      <OnlineRate />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
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

let wsClient = null
let clockTimer = null
let pollTimer = null

function updateClock() {
  const d = new Date()
  // P2-12: 显示毫秒 + "北京时间" 标签
  const p = (n, len = 2) => String(n).padStart(len, '0')
  clock.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
                `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)} 北京时间`
}

onMounted(async () => {
  updateClock()
  // P2-12: 100ms 刷新, 让毫秒位看起来流畅
  clockTimer = setInterval(updateClock, 100)

  // 首屏 REST 拉全量
  await store.initLoad()

  // WebSocket 实时推送
  wsClient = new WsClient(
    (ev) => store.applyEvent(ev),
    (online) => { store.wsConnected = online }
  )
  wsClient.connect()

  // 5 秒轮询兜底 (WS 之外的保险, 校正统计数据)
  pollTimer = setInterval(() => {
    store.pollOverview()
    store.pollAlarmStats()
    store.pollSceneRules()
  }, 5000)

  // P2-10: 键盘快捷键 (F=全屏, Esc=退出全屏, R=重连 WS)
  document.addEventListener('keydown', onKeydown)
})

// P2-10: 键盘事件处理 (输入框中不触发)
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
      if (wsClient) {
        wsClient.close()
        wsClient.connect()
        console.log('[hotkey] WS 重连')
      }
      break
  }
}

onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(pollTimer)
  document.removeEventListener('keydown', onKeydown)
  wsClient && wsClient.close()
})
</script>

<style scoped>
.cell {
  min-height: 0;
  min-width: 0;
}
</style>
