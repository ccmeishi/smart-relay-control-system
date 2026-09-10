<template>
  <div class="panel scene-panel">
    <div class="panel-title">场景联动</div>
    <div class="panel-body">
      <div class="rule-grid">
        <div
          v-for="r in rules"
          :key="r.id"
          class="rule-card"
          :class="{ disabled: !r.enabled, 'rule-flash': store.flashRuleId === r.id }"
        >
          <div class="rule-head">
            <span class="rule-name">{{ r.name }}</span>
            <span class="rule-state" :class="r.enabled ? 'on' : 'off'"></span>
          </div>
          <div class="rule-cond">{{ condText(r) }}</div>
          <div class="rule-foot">
            <span class="trig-count">触发 {{ r.trigger_count }} 次</span>
            <span class="level-badge" :class="r.alarm_level">{{ levelText(r.alarm_level) }}</span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useDashboardStore } from '../stores/dashboard'

const store = useDashboardStore()

// 最多展示 4 张卡片 (取启用优先, 按 id)
const rules = computed(() => {
  const all = [...store.sceneRules].sort((a, b) => Number(b.enabled) - Number(a.enabled) || a.id - b.id)
  return all.slice(0, 4)
})

const OP_TEXT = { '>': '>', '<': '<', '>=': '≥', '<=': '≤', '==': '=', '!=': '≠' }
const KEY_TEXT = {
  temperature: '温度', humidity: '湿度', human: '人感', smoke: '烟雾',
  relay1: '门锁', relay2: '灯1', relay3: '灯2', relay4: '空调'
}
function condText(r) {
  const k = KEY_TEXT[r.trigger_key] || r.trigger_key
  const op = OP_TEXT[r.trigger_operator] || r.trigger_operator
  return `${k} ${op} ${r.trigger_value}`
}
function levelText(l) {
  return { critical: '严重', warning: '警告', info: '提示' }[l] || l
}
</script>

<style scoped>
.scene-panel { height: 100%; }
.rule-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 10px;
}
.rule-card {
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(64,158,255,0.25);
  border-radius: 8px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 6px;
}
.rule-card.disabled {
  border-color: rgba(255,255,255,0.08);
  opacity: 0.5;
}
.rule-head { display: flex; align-items: center; justify-content: space-between; }
.rule-name { font-size: 13px; font-weight: 600; color: #cfe3ff; }
.rule-state { width: 8px; height: 8px; border-radius: 50%; }
.rule-state.on { background: var(--green); box-shadow: 0 0 6px var(--green); }
.rule-state.off { background: #5a6678; }
.rule-cond {
  font-size: 12px; color: var(--text-dim);
  font-family: 'Orbitron', monospace;
}
.rule-foot { display: flex; align-items: center; justify-content: space-between; }
.trig-count { font-size: 11px; color: var(--text-dim); }
.level-badge {
  font-size: 10px; padding: 1px 6px; border-radius: 3px; font-weight: 600;
}
.level-badge.critical { background: rgba(245,108,108,0.2); color: #f56c6c; }
.level-badge.warning { background: rgba(230,162,60,0.2); color: #e6a23c; }
.level-badge.info { background: rgba(64,158,255,0.2); color: #409eff; }
</style>
