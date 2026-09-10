<template>
  <div class="login-page">
    <form class="login-card" @submit.prevent="onLogin">
      <h2>智能继电器控制系统</h2>
      <p class="login-sub">管理后台登录</p>
      <input v-model="username" placeholder="用户名" autocomplete="username" />
      <input v-model="password" type="password" placeholder="密码" autocomplete="current-password" />
      <button type="submit" :disabled="loading">{{ loading ? '登录中…' : '登录' }}</button>
      <p v-if="err" class="login-err">{{ err }}</p>
      <p class="login-hint">默认 admin / admin123 &nbsp;·&nbsp; <a href="/">返回大屏</a></p>
    </form>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()
const username = ref('admin')
const password = ref('')
const loading = ref(false)
const err = ref('')

async function onLogin() {
  err.value = ''
  loading.value = true
  try {
    await auth.login(username.value.trim(), password.value)
    const redirect = route.query.redirect || '/manage'
    router.push(redirect)
  } catch (e) {
    err.value = e.response?.status === 401 ? '用户名或密码错误' : ('登录失败: ' + (e.message || ''))
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-page {
  min-height: 100vh; display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #0f172a, #1e293b);
}
.login-card {
  background: #1e293b; padding: 36px 32px; border-radius: 12px;
  border: 1px solid #334155; width: 340px; box-shadow: 0 10px 40px rgba(0,0,0,.4);
}
.login-card h2 { margin: 0 0 4px; color: #60a5fa; font-size: 20px; }
.login-sub { margin: 0 0 22px; color: #94a3b8; font-size: 13px; }
.login-card input {
  width: 100%; box-sizing: border-box; padding: 10px 12px; margin-bottom: 12px;
  background: #0f172a; border: 1px solid #475569; border-radius: 8px;
  color: #e2e8f0; font-size: 14px;
}
.login-card input:focus { outline: none; border-color: #3b82f6; }
.login-card button {
  width: 100%; padding: 10px; background: #3b82f6; color: #fff; border: none;
  border-radius: 8px; font-size: 15px; cursor: pointer; margin-top: 4px;
}
.login-card button:disabled { opacity: .6; cursor: default; }
.login-err { color: #ef4444; font-size: 13px; margin: 10px 0 0; }
.login-hint { color: #64748b; font-size: 12px; margin: 16px 0 0; text-align: center; }
.login-hint a { color: #60a5fa; text-decoration: none; }
</style>
