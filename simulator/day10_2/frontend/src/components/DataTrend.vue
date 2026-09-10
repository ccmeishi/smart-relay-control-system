<template>
  <div class="panel">
    <div class="panel-title">数据趋势 · 实时采集</div>
    <div class="panel-body">
      <div class="tabs">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="tab"
          :class="{ active: active === t.key }"
          @click="active = t.key"
        >{{ t.label }}</button>
      </div>
      <div ref="chartEl" class="chart"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import { useDashboardStore } from '../stores/dashboard'

const store = useDashboardStore()
const chartEl = ref(null)
let chart = null

const tabs = [
  { key: 'temperature', label: '温度' },
  { key: 'humidity', label: '湿度' },
  { key: 'human', label: '人感' },
  { key: 'smoke', label: '烟雾' }
]
const active = ref('temperature')

function render() {
  if (!chart) return
  const points = store.history[active.value] || []
  const data = points.map((p) => {
    // recorded_at: "YYYY-MM-DDTHH:MM:SS" (UTC) 转本地时间给 time 轴
    const t = p.recorded_at ? p.recorded_at.replace(' ', 'T') + 'Z' : null
    return [t, parseFloat(p.value)]
  }).filter((d) => !isNaN(d[1]))

  chart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: 50, right: 24, top: 24, bottom: 36 },
    xAxis: {
      type: 'time',
      axisLabel: { color: '#8a97a8', fontSize: 11,
        formatter: (v) => { const d = new Date(v); return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}` } },
      axisLine: { lineStyle: { color: '#33415c' } }
    },
    yAxis: {
      type: 'value',
      scale: true,
      axisLabel: { color: '#8a97a8', fontSize: 11 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.06)' } }
    },
    series: [{
      type: 'line',
      smooth: true,
      showSymbol: false,
      data,
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(64,158,255,0.4)' },
          { offset: 1, color: 'rgba(64,158,255,0.02)' }
        ])
      },
      lineStyle: { color: '#409eff', width: 2 }
    }]
  }, true)
}

onMounted(async () => {
  await nextTick()
  chart = echarts.init(chartEl.value)
  render()
  window.addEventListener('resize', resize)
})
function resize() { chart && chart.resize() }
onUnmounted(() => { window.removeEventListener('resize', resize); chart && chart.dispose() })

watch(active, render)
watch(() => store.history, render, { deep: true })
</script>

<style scoped>
.tabs { display: flex; gap: 8px; margin-bottom: 8px; }
.tab {
  padding: 5px 16px;
  font-size: 13px;
  border-radius: 16px;
  border: 1px solid rgba(255,255,255,0.12);
  background: transparent;
  color: var(--text-dim);
  transition: all 0.2s;
}
.tab.active {
  background: rgba(64,158,255,0.2);
  border-color: var(--blue);
  color: #6db3ff;
  box-shadow: 0 0 8px rgba(64,158,255,0.3);
}
.chart { flex: 1; min-height: 0; width: 100%; }
</style>
