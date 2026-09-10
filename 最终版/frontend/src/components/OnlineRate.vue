<template>
  <div class="panel">
    <div class="panel-title">设备在线率</div>
    <div class="panel-body">
      <div ref="chartEl" class="chart"></div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { useDashboardStore } from '../stores/dashboard'

const store = useDashboardStore()
const chartEl = ref(null)
let chart = null

function render() {
  if (!chart) return
  const { online, offline, online_rate } = store.overview
  chart.setOption({
    series: [{
      type: 'pie',
      radius: ['68%', '88%'],
      center: ['50%', '50%'],
      avoidLabelOverlap: false,
      label: { show: false },
      data: [
        { value: online, name: '在线', itemStyle: { color: '#67c23a' } },
        { value: offline, name: '离线', itemStyle: { color: '#f56c6c' } }
      ]
    }],
    graphic: [{
      type: 'text',
      left: 'center', top: 'center',
      style: {
        text: `${online_rate}%`,
        fontSize: 26,
        fontWeight: 700,
        fill: '#fff',
        textAlign: 'center',
        textVerticalAlign: 'middle'
      }
    }, {
      type: 'text',
      left: 'center', top: '62%',
      style: {
        text: `在线 ${online} / ${online + offline}`,
        fontSize: 12,
        fill: '#8a97a8',
        textAlign: 'center'
      }
    }]
  })
}

onMounted(() => {
  chart = echarts.init(chartEl.value)
  render()
  window.addEventListener('resize', resize)
})

function resize() { chart && chart.resize() }

onUnmounted(() => {
  window.removeEventListener('resize', resize)
  chart && chart.dispose()
})

watch(() => store.overview, render, { deep: true })
</script>

<style scoped>
.chart { width: 100%; height: 100%; min-height: 120px; }
</style>
