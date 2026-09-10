<template>
  <div class="page">
    <div class="page-head">
      <h2>场景规则 ({{ list.length }})</h2>
      <span class="hint">规则 CRUD 由后端 db.py 提供, 此页为只读监控视图 (触发次数持久化于 DB)</span>
    </div>
    <table class="tbl">
      <thead><tr><th>ID</th><th>规则</th><th>触发条件</th><th>动作</th><th>告警级别</th><th>状态</th><th>触发次数</th><th>上次触发</th></tr></thead>
      <tbody>
        <tr v-for="r in list" :key="r.id">
          <td>{{ r.id }}</td>
          <td><strong>{{ r.name }}</strong><div class="desc">{{ r.description }}</div></td>
          <td><code>{{ r.trigger_key }} {{ r.trigger_operator }} {{ r.trigger_value }}</code></td>
          <td>{{ r.action_type }}{{ r.action_target ? '(' + r.action_target + '=' + r.action_value + ')' : '' }}</td>
          <td><span :class="['lvl', r.alarm_level]">{{ levelLabel(r.alarm_level) }}</span></td>
          <td><span :class="['tag', r.enabled ? 'ok' : 'off']">{{ r.enabled ? '启用' : '禁用' }}</span></td>
          <td class="cnt">{{ r.trigger_count }}</td>
          <td>{{ r.last_triggered || '—' }}</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import http from '../api/http'
const list = ref([])
const LABELS = { info: '提示', warning: '警告', critical: '严重' }
const levelLabel = (l) => LABELS[l] || l
async function load() { list.value = await http.sceneRules() }
onMounted(load)
</script>

<style scoped>
.page { color: #e2e8f0; }
.page-head { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
h2 { margin: 0 0 16px; color: #60a5fa; }
.hint { color: #64748b; font-size: 12px; }
.tbl { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; }
.tbl th, .tbl td { padding: 9px 10px; text-align: left; border-bottom: 1px solid #334155; font-size: 13px; vertical-align: top; }
.tbl th { color: #94a3b8; font-weight: 500; }
.tbl code { background: #0f172a; padding: 1px 6px; border-radius: 4px; color: #60a5fa; }
.desc { color: #64748b; font-size: 12px; margin-top: 2px; }
.lvl { padding: 2px 8px; border-radius: 10px; font-size: 12px; color: #fff; }
.lvl.info { background: #3b82f6; }
.lvl.warning { background: #f59e0b; }
.lvl.critical { background: #ef4444; }
.tag { padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.tag.ok { background: #16a34a; color: #fff; }
.tag.off { background: #475569; color: #cbd5e1; }
.cnt { font-variant-numeric: tabular-nums; font-weight: 600; color: #fbbf24; }
</style>
