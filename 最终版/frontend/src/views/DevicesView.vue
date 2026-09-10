<template>
  <div class="page">
    <div class="page-head">
      <h2>设备控制台</h2>
      <div v-if="auth.isAdmin" class="all-btns">
        <button @click="allAction('on')" :disabled="busy">一键全开</button>
        <button @click="allAction('off')" :disabled="busy" class="danger">一键全关</button>
      </div>
    </div>

    <h3>继电器</h3>
    <div class="relay-grid">
      <div v-for="r in data.relay_cards" :key="r.key" class="relay-card">
        <div class="rc-head">
          <strong>{{ r.desc || r.key }}</strong>
          <span :class="['rc-state', r.value ? 'on' : 'off']">{{ r.value ? '开' : '关' }}</span>
        </div>
        <div class="rc-meta">{{ r.product }}/{{ r.device }} · {{ r.enabled ? '启用' : '禁用' }}</div>
        <button @click="toggle(r)" :disabled="busy">{{ r.value ? '关闭' : '开启' }}</button>
      </div>
    </div>

    <h3>传感器</h3>
    <div class="sensor-grid">
      <div v-for="s in data.sensor_cards" :key="s.key" class="sensor-card">
        <div class="sc-name">{{ s.desc || s.key }}</div>
        <div class="sc-val">{{ s.value }} <small>{{ s.unit }}</small></div>
        <div class="sc-meta">{{ s.product }}</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const data = ref({ relay_cards: [], sensor_cards: [] })
const busy = ref(false)

async function load() {
  data.value = await http.devices()
}
async function toggle(r) {
  busy.value = true
  try {
    await http.toggleRelay(r.key, r.value ? '0' : '1')
    await load()
  } finally { busy.value = false }
}
async function allAction(action) {
  busy.value = true
  try { await http.devicesAll(action); await load() }
  catch (e) { alert(e.response?.data?.error || '操作失败') }
  finally { busy.value = false }
}
onMounted(load)
</script>

<style scoped>
.page { color: #e2e8f0; }
.page-head { display: flex; justify-content: space-between; align-items: center; }
h2 { margin: 0 0 16px; color: #60a5fa; }
h3 { margin: 24px 0 12px; color: #94a3b8; font-size: 15px; border-bottom: 1px solid #334155; padding-bottom: 6px; }
.all-btns { display: flex; gap: 8px; }
.all-btns button { padding: 7px 14px; background: #3b82f6; color: #fff; border: none; border-radius: 6px; cursor: pointer; }
.all-btns button.danger { background: #ef4444; }
.relay-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 12px; }
.relay-card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 14px; }
.rc-head { display: flex; justify-content: space-between; align-items: center; }
.rc-state { font-size: 13px; padding: 2px 10px; border-radius: 12px; }
.rc-state.on { background: #16a34a; color: #fff; }
.rc-state.off { background: #475569; color: #cbd5e1; }
.rc-meta { color: #64748b; font-size: 12px; margin: 6px 0 10px; }
.relay-card button { width: 100%; padding: 7px; background: #334155; color: #e2e8f0; border: 1px solid #475569; border-radius: 6px; cursor: pointer; }
.relay-card button:hover { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.sensor-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px; }
.sensor-card { background: #1e293b; border: 1px solid #334155; border-radius: 10px; padding: 14px; }
.sc-name { color: #94a3b8; font-size: 13px; }
.sc-val { font-size: 24px; font-weight: 600; color: #e2e8f0; margin: 6px 0; }
.sc-val small { font-size: 13px; color: #64748b; font-weight: 400; }
.sc-meta { color: #64748b; font-size: 12px; }
</style>
