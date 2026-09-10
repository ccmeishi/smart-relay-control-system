<template>
  <div class="page">
    <div class="page-head">
      <h2>用户管理 ({{ list.length }})</h2>
      <button @click="openAdd" class="add-btn">+ 新增用户</button>
    </div>
    <table class="tbl">
      <thead><tr><th>ID</th><th>用户名</th><th>显示名</th><th>角色</th><th>创建时间</th><th>操作</th></tr></thead>
      <tbody>
        <tr v-for="u in list" :key="u.id">
          <td>{{ u.id }}</td>
          <td><code>{{ u.username }}</code></td>
          <td>{{ u.display_name || '—' }}</td>
          <td><select :value="u.role" @change="setRole(u, $event.target.value)" :disabled="u.id === auth.user?.id">
            <option value="user">user</option><option value="admin">admin</option>
          </select></td>
          <td>{{ u.created_at }}</td>
          <td class="ops">
            <button @click="reset(u)">重置密码</button>
            <button @click="del(u)" class="del" :disabled="u.id === auth.user?.id">删除</button>
          </td>
        </tr>
      </tbody>
    </table>

    <div v-if="showForm" class="modal-bg" @click.self="showForm = false">
      <form class="modal" @submit.prevent="save">
        <h3>新增用户</h3>
        <label>用户名<input v-model="form.username"></label>
        <label>密码<input v-model="form.password" type="password"></label>
        <label>角色<select v-model="form.role"><option value="user">user</option><option value="admin">admin</option></select></label>
        <label>显示名<input v-model="form.display_name"></label>
        <p v-if="err" class="err">{{ err }}</p>
        <div class="modal-actions"><button type="button" @click="showForm = false">取消</button><button type="submit" class="primary">创建</button></div>
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
async function load() { list.value = await http.users() }
function openAdd() { form.value = { username: '', password: '', role: 'user', display_name: '' }; err.value = ''; showForm.value = true }
async function save() {
  err.value = ''
  try { await http.addUser(form.value); showForm.value = false; await load() }
  catch (e) { err.value = e.response?.data?.error || '创建失败' }
}
async function setRole(u, role) { try { await http.updateUserRole(u.id, role); await load() } catch (e) { alert(e.response?.data?.error) } }
async function reset(u) {
  const p = prompt(`为 ${u.username} 设置新密码 (≥6位):`)
  if (!p) return
  try { await http.resetPassword(u.id, p); alert('密码已重置') } catch (e) { alert(e.response?.data?.error) }
}
async function del(u) { if (!confirm(`删除用户 ${u.username}?`)) return; await http.deleteUser(u.id); await load() }
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
.tbl select { background: #0f172a; color: #e2e8f0; border: 1px solid #475569; border-radius: 5px; padding: 3px; }
.ops button { margin-right: 4px; padding: 3px 9px; background: #334155; color: #e2e8f0; border: 1px solid #475569; border-radius: 5px; cursor: pointer; font-size: 12px; }
.ops button.del { background: #7f1d1d; border-color: #991b1b; }
.ops button:disabled { opacity: .4; cursor: default; }
.modal-bg { position: fixed; inset: 0; background: rgba(0,0,0,.6); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: #1e293b; padding: 24px; border-radius: 12px; width: 340px; border: 1px solid #334155; }
.modal h3 { margin: 0 0 16px; color: #60a5fa; }
.modal label { display: block; margin-bottom: 10px; font-size: 13px; color: #94a3b8; }
.modal input, .modal select { width: 100%; box-sizing: border-box; padding: 8px; margin-top: 4px; background: #0f172a; border: 1px solid #475569; border-radius: 6px; color: #e2e8f0; }
.err { color: #ef4444; font-size: 13px; }
.modal-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 8px; }
.modal-actions button { padding: 7px 16px; border-radius: 6px; cursor: pointer; background: #334155; color: #e2e8f0; border: 1px solid #475569; }
.modal-actions button.primary { background: #3b82f6; color: #fff; border-color: #3b82f6; }
</style>
