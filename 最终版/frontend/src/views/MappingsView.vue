<template>
  <div class="page">
    <div class="page-head">
      <h2>路由映射 ({{ list.length }})</h2>
      <button v-if="auth.isAdmin" @click="openAdd" class="add-btn">+ 新增映射</button>
    </div>
    <table class="tbl">
      <thead><tr><th>ID</th><th>gateway_key</th><th>product_id</th><th>device_id</th><th>property</th><th>描述</th><th>状态</th><th v-if="auth.isAdmin">操作</th></tr></thead>
      <tbody>
        <tr v-for="m in list" :key="m.id">
          <td>{{ m.id }}</td>
          <td><code>{{ m.gateway_key }}</code></td>
          <td>{{ m.product_id }}</td>
          <td>{{ m.device_id }}</td>
          <td>{{ m.property_name }}</td>
          <td>{{ m.description }}</td>
          <td><span :class="['tag', m.enabled ? 'ok' : 'off']">{{ m.enabled ? '启用' : '禁用' }}</span></td>
          <td v-if="auth.isAdmin" class="ops">
            <button @click="toggle(m)">切换</button>
            <button @click="edit(m)">编辑</button>
            <button @click="del(m)" class="del">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="showForm" class="modal-bg" @click.self="showForm = false">
      <form class="modal" @submit.prevent="save">
        <h3>{{ form.id ? '编辑映射' : '新增映射' }}</h3>
        <label>gateway_key<input v-model="form.gateway_key" placeholder="relay1 / temperature"></label>
        <label>product_id<input v-model="form.product_id" placeholder="lock-cc"></label>
        <label>device_id<input v-model="form.device_id" placeholder="lock001"></label>
        <label>property_name<input v-model="form.property_name" placeholder="switch"></label>
        <label>描述<input v-model="form.description"></label>
        <label v-if="form.id"><input type="checkbox" v-model="form.enabled"> 启用</label>
        <p v-if="err" class="err">{{ err }}</p>
        <div class="modal-actions"><button type="button" @click="showForm = false">取消</button><button type="submit" class="primary">保存</button></div>
      </form>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import http from '../api/http'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const list = ref([])
const showForm = ref(false)
const form = ref({})
const err = ref('')

async function load() { list.value = await http.mappings() }
function openAdd() { form.value = { gateway_key: '', product_id: '', device_id: '', property_name: '', description: '', enabled: true }; err.value = ''; showForm.value = true }
function edit(m) { form.value = { ...m, enabled: !!m.enabled }; err.value = ''; showForm.value = true }
async function save() {
  err.value = ''
  try {
    if (form.value.id) await http.updateMapping(form.value.id, form.value)
    else await http.addMapping(form.value)
    showForm.value = false
    await load()
  } catch (e) { err.value = e.response?.data?.error || '保存失败' }
}
async function toggle(m) { await http.toggleMapping(m.id); await load() }
async function del(m) {
  if (!confirm(`删除映射 ${m.gateway_key}?`)) return
  await http.deleteMapping(m.id); await load()
}
onMounted(load)
</script>

<style scoped>
.page { color: #e2e8f0; }
.page-head { display: flex; justify-content: space-between; align-items: center; }
h2 { margin: 0 0 16px; color: #60a5fa; }
.add-btn { padding: 7px 14px; background: #3b82f6; color: #fff; border: none; border-radius: 6px; cursor: pointer; }
.tbl { width: 100%; border-collapse: collapse; background: #1e293b; border-radius: 8px; overflow: hidden; }
.tbl th, .tbl td { padding: 9px 10px; text-align: left; border-bottom: 1px solid #334155; font-size: 13px; }
.tbl th { color: #94a3b8; font-weight: 500; }
.tbl code { background: #0f172a; padding: 1px 6px; border-radius: 4px; color: #60a5fa; }
.tag { padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.tag.ok { background: #16a34a; color: #fff; }
.tag.off { background: #475569; color: #cbd5e1; }
.ops button { margin-right: 4px; padding: 3px 9px; background: #334155; color: #e2e8f0; border: 1px solid #475569; border-radius: 5px; cursor: pointer; font-size: 12px; }
.ops button.del { background: #7f1d1d; border-color: #991b1b; }
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,.6); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: #1e293b; padding: 24px; border-radius: 12px; width: 380px; border: 1px solid #334155; }
.modal h3 { margin: 0 0 16px; color: #60a5fa; }
.modal label { display: block; margin-bottom: 10px; font-size: 13px; color: #94a3b8; }
.modal input[type=text] { width: 100%; box-sizing: border-box; padding: 8px; margin-top: 4px; background: #0f172a; border: 1px solid #475569; border-radius: 6px; color: #e2e8f0; }
.modal input { color: #e2e8f0; }
.err { color: #ef4444; font-size: 13px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.modal-actions button { padding: 7px 16px; border-radius: 6px; cursor: pointer; background: #334155; color: #e2e8f0; border: 1px solid #475569; }
.modal-actions button.primary { background: #3b82f6; color: #fff; border-color: #3b82f6; }
</style>
