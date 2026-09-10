<template>
  <div class="page">
    <h2>网关配置 (config.json)</h2>
    <p class="hint">MQTT/WiFi/网关凭据唯一可信源. 修改后 ESP32 需重启生效.</p>
    <div v-if="cfg" class="cfg-form">
      <label>WiFi SSID<input v-model="cfg.wifi_ssid"></label>
      <label>WiFi 密码<input v-model="cfg.wifi_pass" type="password" placeholder="留空/****** 表示不改"></label>
      <label>MQTT Host<input v-model="cfg.mqtt_host"></label>
      <label>MQTT Port<input v-model.number="cfg.mqtt_port" type="number"></label>
      <label>product_id<input v-model="cfg.product_id"></label>
      <label>device_id<input v-model="cfg.device_id"></label>
      <div class="raw">
        <span class="raw-label">完整 config.json (只读)</span>
        <pre>{{ rawJson }}</pre>
      </div>
      <p v-if="err" class="err">{{ err }}</p>
      <p v-if="msg" class="ok">{{ msg }}</p>
      <button @click="save" class="save-btn">保存配置</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import http from '../api/http'
const cfg = ref(null)
const is_admin = ref(false)
const err = ref('')
const msg = ref('')
const rawJson = computed(() => cfg.value ? JSON.stringify(cfg.value, null, 2) : '')
async function load() {
  const r = await http.configPoints()
  cfg.value = r.config
  is_admin.value = r.is_admin
}
async function save() {
  err.value = ''; msg.value = ''
  try { const r = await http.saveConfig(cfg.value); msg.value = r.msg || '已保存'; await load() }
  catch (e) { err.value = e.response?.data?.error || '保存失败' }
}
onMounted(load)
</script>

<style scoped>
.page { color: #e2e8f0; max-width: 720px; }
h2 { margin: 0 0 8px; color: #60a5fa; }
.hint { color: #64748b; font-size: 13px; margin: 0 0 18px; }
.cfg-form label { display: block; margin-bottom: 12px; font-size: 13px; color: #94a3b8; }
.cfg-form input { width: 100%; box-sizing: border-box; padding: 8px; margin-top: 4px; background: #0f172a; border: 1px solid #475569; border-radius: 6px; color: #e2e8f0; }
.raw { margin: 16px 0; }
.raw-label { display: block; color: #94a3b8; font-size: 13px; margin-bottom: 6px; }
.raw pre { background: #0f172a; border: 1px solid #334155; border-radius: 8px; padding: 12px; font-size: 12px; color: #cbd5e1; overflow: auto; max-height: 280px; margin: 0; }
.err { color: #ef4444; font-size: 13px; }
.ok { color: #16a34a; font-size: 13px; }
.save-btn { padding: 9px 20px; background: #3b82f6; color: #fff; border: none; border-radius: 8px; cursor: pointer; font-size: 14px; }
</style>
