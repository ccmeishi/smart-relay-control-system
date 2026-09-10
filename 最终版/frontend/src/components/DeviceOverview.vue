<template>
  <div class="panel">
    <div class="panel-title">设备概览</div>
    <div class="panel-body">
      <div class="total-wrap">
        <div class="total-label">设备总数</div>
        <div class="big-num total-num">{{ store.overview.total }}</div>
      </div>
      <div class="stat-row">
        <div class="stat-card online">
          <div class="stat-num big-num">{{ store.overview.online }}</div>
          <div class="stat-name">在线设备</div>
        </div>
        <div class="stat-card offline">
          <div class="stat-num big-num">{{ store.overview.offline }}</div>
          <div class="stat-name">离线设备</div>
        </div>
      </div>
      <div class="rate-bar-wrap">
        <div class="rate-bar-label">
          <span>在线率</span>
          <span class="rate-val">{{ store.overview.online_rate }}%</span>
        </div>
        <div class="rate-bar">
          <div class="rate-bar-fill" :style="{ width: store.overview.online_rate + '%' }"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useDashboardStore } from '../stores/dashboard'
const store = useDashboardStore()
</script>

<style scoped>
/* 让三块均匀撑满 panel-body 高度, 不留空白 */
.panel-body { justify-content: space-between; }

.total-wrap { text-align: center; flex-shrink: 0; }
.total-label { font-size: 15px; color: #b8c4d4; margin-bottom: 6px; letter-spacing: 2px; }
.total-num { font-size: 52px; line-height: 1; }

.stat-row { display: flex; gap: 14px; flex-shrink: 0; }
.stat-card {
  flex: 1;
  background: rgba(255,255,255,0.04);
  border: 1px solid rgba(255,255,255,0.1);
  border-radius: 10px;
  padding: 14px 10px;
  text-align: center;
}
.stat-card.online { border-color: rgba(103,194,58,0.4); background: rgba(103,194,58,0.06); }
.stat-card.offline { border-color: rgba(245,108,108,0.4); background: rgba(245,108,108,0.06); }
.stat-num { font-size: 34px; }
.stat-card.online .stat-num { color: var(--green); text-shadow: 0 0 10px rgba(103,194,58,0.5); }
.stat-card.offline .stat-num { color: var(--red); text-shadow: 0 0 10px rgba(245,108,108,0.5); }
.stat-name { font-size: 14px; color: #b8c4d4; margin-top: 6px; letter-spacing: 1px; }

/* rate-bar-wrap 吃掉剩余空间, 紧贴 stat-row, 底部留点呼吸空间 */
.rate-bar-wrap { flex-shrink: 0; padding-top: 4px; padding-bottom: 4px; }
.rate-bar-label {
  display: flex; justify-content: space-between;
  font-size: 14px; color: #b8c4d4; margin-bottom: 8px;
}
.rate-val { color: #6db3ff; font-weight: 600; font-size: 16px; }
.rate-bar {
  height: 12px; border-radius: 6px;
  background: rgba(255,255,255,0.08);
  overflow: hidden;
}
.rate-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #409eff, #67c23a);
  border-radius: 6px;
  box-shadow: 0 0 10px rgba(103,194,58,0.6);
  transition: width 0.6s ease;
}
</style>
