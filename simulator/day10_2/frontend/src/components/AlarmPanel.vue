<template>
  <div class="panel">
    <div class="panel-title">告警信息</div>
    <div class="panel-body">
      <!-- 顶部 3 统计 -->
      <div class="alarm-stats">
        <div class="alarm-stat">
          <div class="num big-num">{{ store.alarmStats.total }}</div>
          <div class="lbl">今日告警</div>
        </div>
        <div class="alarm-stat active">
          <div class="num big-num">{{ store.alarmStats.active }}</div>
          <div class="lbl">未处理</div>
        </div>
        <div class="alarm-stat done">
          <div class="num big-num">{{ store.alarmStats.acknowledged + store.alarmStats.cleared }}</div>
          <div class="lbl">已处理</div>
        </div>
      </div>

      <!-- 级别分布饼图 -->
      <div ref="pieEl" class="pie"></div>

      <!-- 告警列表 -->
      <div class="alarm-list">
        <div
          v-for="a in store.recentAlarms"
          :key="a.id"
          class="alarm-item"
          :class="[levelClass(a.level), { 'critical-flash': store.flashAlarmId === a.id && a.level === 'critical', 'fade-in': store.flashAlarmId === a.id }]"
        >
          <span class="lv-tag">{{ levelText(a.level) }}</span>
          <span class="alarm-msg">{{ a.message || a.rule_name }}</span>
          <span class="alarm-time">{{ fmtTime(a.triggered_at) }}</span>
        </div>
        <div v-if="store.recentAlarms.length === 0" class="empty">暂无告警</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'
import * as echarts from 'echarts'
import { useDashboardStore } from '../stores/dashboard'

const store = useDashboardStore()
const pieEl = ref(null)
let chart = null

const LEVEL = {
  critical: { text: '严重', cls: 'lv-critical' },
  warning: { text: '警告', cls: 'lv-warning' },
  info: { text: '提示', cls: 'lv-info' }
}
function levelText(l) { return LEVEL[l]?.text || l }
function levelClass(l) { return LEVEL[l]?.cls || 'lv-info' }
function fmtTime(t) {
  if (!t) return ''
  // SQLite "YYYY-MM-DD HH:MM:SS" → 取 MM-DD HH:MM
  return String(t).replace('T', ' ').slice(5, 16)
}

function renderPie() {
  if (!chart) return
  const bl = store.alarmStats.by_level || {}
  chart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: {
      bottom: 0, icon: 'circle', itemWidth: 8, itemHeight: 8,
      textStyle: { color: '#8a97a8', fontSize: 11 }
    },
    series: [{
      type: 'pie',
      radius: ['45%', '70%'],
      center: ['50%', '42%'],
      label: { show: false },
      data: [
        { value: bl.info || 0, name: '提示', itemStyle: { color: '#409eff' } },
        { value: bl.warning || 0, name: '警告', itemStyle: { color: '#e6a23c' } },
        { value: bl.critical || 0, name: '严重', itemStyle: { color: '#f56c6c' } }
      ]
    }]
  })
}

onMounted(() => {
  chart = echarts.init(pieEl.value)
  renderPie()
  window.addEventListener('resize', resize)
})
function resize() { chart && chart.resize() }
onUnmounted(() => { window.removeEventListener('resize', resize); chart && chart.dispose() })
watch(() => store.alarmStats, renderPie, { deep: true })
</script>

<style scoped>
.alarm-stats { display: flex; gap: 10px; margin-bottom: 8px; }
.alarm-stat {
  flex: 1; text-align: center;
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(255,255,255,0.08);
  border-radius: 8px; padding: 8px 0;
}
.alarm-stat.active { border-color: rgba(245,108,108,0.4); }
.alarm-stat.done { border-color: rgba(103,194,58,0.4); }
.num { font-size: 24px; }
.alarm-stat.active .num { color: var(--red); }
.alarm-stat.done .num { color: var(--green); }
.lbl { font-size: 12px; color: var(--text-dim); margin-top: 2px; }

.pie { height: 130px; flex-shrink: 0; }

.alarm-list {
  flex: 1; overflow-y: auto;
  border-top: 1px solid rgba(255,255,255,0.06);
  padding-top: 6px;
}
.alarm-item {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 4px;
  border-bottom: 1px solid rgba(255,255,255,0.04);
  font-size: 12px;
}
.lv-tag {
  flex-shrink: 0;
  padding: 1px 7px; border-radius: 3px;
  font-size: 11px; font-weight: 600;
}
.lv-critical .lv-tag { background: rgba(245,108,108,0.2); color: #f56c6c; border: 1px solid rgba(245,108,108,0.5); }
.lv-warning .lv-tag { background: rgba(230,162,60,0.2); color: #e6a23c; border: 1px solid rgba(230,162,60,0.5); }
.lv-info .lv-tag { background: rgba(64,158,255,0.2); color: #409eff; border: 1px solid rgba(64,158,255,0.5); }
.alarm-msg { flex: 1; color: #c9d4e3; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.alarm-time { flex-shrink: 0; color: var(--text-dim); font-family: monospace; }
.empty { text-align: center; color: var(--text-dim); font-size: 13px; padding: 20px 0; }
</style>
