<template>
  <div class="panel">
    <div class="panel-title">通道状态 · 继电器控制</div>
    <div class="panel-body">
      <div class="relay-grid">
        <button
          v-for="r in relays"
          :key="r.key"
          class="relay-btn"
          :class="{ on: isOn(r.key), disabled: busy === r.key }"
          :disabled="busy === r.key"
          @click="onToggle(r.key)"
        >
          <svg viewBox="0 0 24 24" class="relay-icon">
            <path :fill="isOn(r.key) ? '#67c23a' : '#5a6678'"
              d="M12 2a7 7 0 0 0-7 7v6a3 3 0 0 0 3 3h8a3 3 0 0 0 3-3V9a7 7 0 0 0-7-7zm-3 7a1 1 0 0 1 1-1h4a1 1 0 1 1 0 2h-4a1 1 0 0 1-1-1z"/>
          </svg>
          <div class="relay-name">{{ r.name }}</div>
          <div class="relay-state">{{ isOn(r.key) ? 'ON' : 'OFF' }}</div>
        </button>
      </div>
      <div class="hint">点击按钮切换继电器 (下行 MQTT 控制)</div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useDashboardStore } from '../stores/dashboard'

const store = useDashboardStore()
const busy = ref(null)

const relays = [
  { key: 'relay1', name: '通道1 · 门锁' },
  { key: 'relay2', name: '通道2 · 灯1' },
  { key: 'relay3', name: '通道3 · 灯2' },
  { key: 'relay4', name: '通道4 · 空调' }
]

function isOn(key) {
  const v = store.deviceStatus[key]
  return v === '1' || v === 1 || v === true
}

async function onToggle(key) {
  if (busy.value) return
  busy.value = key
  await store.toggleRelay(key)
  // 500ms 防抖
  setTimeout(() => { busy.value = null }, 500)
}
</script>

<style scoped>
.relay-grid {
  flex: 1;
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 12px;
}
.relay-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  border-radius: 10px;
  border: 1px solid rgba(255,255,255,0.1);
  background: rgba(255,255,255,0.03);
  color: var(--text-dim);
  transition: all 0.15s ease;
}
.relay-btn:active { transform: scale(0.96); }
.relay-btn.on {
  border-color: rgba(103,194,58,0.6);
  background: rgba(103,194,58,0.12);
  box-shadow: 0 0 16px rgba(103,194,58,0.25) inset, 0 0 10px rgba(103,194,58,0.2);
}
.relay-icon { width: 34px; height: 34px; }
.relay-name { font-size: 14px; font-weight: 600; color: #cfe3ff; }
.relay-state {
  font-family: 'Orbitron', monospace;
  font-size: 18px; font-weight: 700;
  color: #5a6678;
}
.relay-btn.on .relay-state { color: var(--green); text-shadow: 0 0 8px rgba(103,194,58,0.6); }
.relay-btn.disabled { opacity: 0.6; cursor: wait; }
.hint { font-size: 12px; color: var(--text-dim); text-align: center; margin-top: 10px; }
</style>
