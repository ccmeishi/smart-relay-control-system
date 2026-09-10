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

    <!-- 左列 -->
    <DeviceOverview class="cell" />
    <ChannelStatus class="cell" style="grid-column: 1; grid-row: 3;" />

    <!-- 中列 -->
    <DataTrend class="cell" style="grid-column: 2; grid-row: 2 / 4;" />

    <!-- 右列 -->
    <AlarmPanel class="cell" style="grid-column: 3; grid-row: 2;" />
    <div class="cell" style="grid-column: 3; grid-row: 3; display: grid; grid-template-rows: 1fr 1fr; gap: 14px;">
      <SceneRules />
      <OnlineRate />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import { useDashboardStore } from './stores/dashboard'
import { WsClient } from './api/ws'
import DeviceOverview from './components/DeviceOverview.vue'
import ChannelStatus from './components/ChannelStatus.vue'
import AlarmPanel from './components/AlarmPanel.vue'
import DataTrend from './components/DataTrend.vue'
import SceneRules from './components/SceneRules.vue'
import OnlineRate from './components/OnlineRate.vue'

const store = useDashboardStore()
const clock = ref('')

let wsClient = null
let clockTimer = null
let pollTimer = null

function updateClock() {
  const d = new Date()
  const p = (n) => String(n).padStart(2, '0')
  clock.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ` +
                `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

onMounted(async () => {
  updateClock()
  clockTimer = setInterval(updateClock, 1000)

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
})

onUnmounted(() => {
  clearInterval(clockTimer)
  clearInterval(pollTimer)
  wsClient && wsClient.close()
})
</script>

<style scoped>
.cell {
  min-height: 0;
  min-width: 0;
}
</style>
