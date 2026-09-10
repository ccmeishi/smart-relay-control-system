<template>
  <div class="page">
    <h2>在线会话</h2>
    <div class="stats-row">
      <div class="stat"><span>当前在线</span><strong>{{ data.online_count }}</strong></div>
    </div>
    <h3>在线用户 ({{ data.online?.length || 0 }})</h3>
    <table class="tbl">
      <thead><tr><th>session_id</th><th>用户</th><th>IP</th><th>登录时间</th><th>最后活跃</th></tr></thead>
      <tbody>
        <tr v-for="s in data.online || []" :key="s.id"><td>{{ s.id }}</td><td><code>{{ s.username }}</code></td><td>{{ s.ip }}</td><td>{{ s.login_at }}</td><td>{{ s.last_seen }}</td></tr>
        <tr v-if="!data.online?.length"><td colspan="5" class="empty">暂无在线用户</td></tr>
      </tbody>
    </table>
    <h3>最近登录历史</h3>
    <table class="tbl">
      <thead><tr><th>ID</th><th>用户</th><th>IP</th><th>登录</th><th>登出</th><th>最后活跃</th><th>状态</th></tr></thead>
      <tbody>
        <tr v-for="s in data.recent || []" :key="s.id"><td>{{ s.id }}</td><td><code>{{ s.username }}</code></td><td>{{ s.ip }}</td><td>{{ s.login_at }}</td><td>{{ s.logout_at || '—' }}</td><td>{{ s.last_seen }}</td><td><span :class="['tag', s.status === 'online' ? 'ok' : 'off']">{{ s.status }}</span></td></tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import http from '../api/http'
const data = ref({})
async function load() { data.value = await http.sessions() }
onMounted(load)
</script>

<style scoped>
.page { color: #e2e8f0; }
h2 { margin: 0 0 16px; color: #60a5fa; }
h3 { margin: 22px 0 10px; color: #94a3b8; font-size: 15px; }
.stats-row { display: flex; gap: 12px; margin-bottom: 8px; }
.stat { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px 20px; }
.stat span { display: block; color: #94a3b8; font-size: 12px; }
.stat strong { font-size: 22px; color: #60a5fa; }
.tbl { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; margin-bottom: 16px; }
.tbl th, .tbl td { padding: 8px 10px; text-align: left; border-bottom: 1px solid #334155; font-size: 13px; }
.tbl th { color: #94a3b8; font-weight: 500; }
.tbl code { background: #0f172a; padding: 1px 6px; border-radius: 4px; color: #60a5fa; }
.tag { padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.tag.ok { background: #16a34a; color: #fff; }
.tag.off { background: #475569; color: #cbd5e1; }
.empty { color: #64748b; text-align: center; }
</style>
