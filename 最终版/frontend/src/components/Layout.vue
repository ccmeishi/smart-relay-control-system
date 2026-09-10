<template>
  <div class="mgmt">
    <nav class="topnav">
      <div class="nav-brand">智能继电器控制系统 · 管理后台</div>
      <div class="nav-links">
        <router-link to="/manage/devices">设备控制台</router-link>
        <router-link to="/manage/mappings">路由映射</router-link>
        <router-link to="/manage/scenes">场景规则</router-link>
        <router-link v-if="auth.isAdmin" to="/manage/users">用户管理</router-link>
        <router-link v-if="auth.isAdmin" to="/manage/sessions">在线会话</router-link>
        <router-link v-if="auth.isAdmin" to="/manage/config">网关配置</router-link>
      </div>
      <div class="nav-user">
        <a href="/" class="nav-dash" title="返回大屏">📊 大屏</a>
        <span class="nav-name">{{ auth.user?.display_name }}
          <small>({{ auth.user?.role }})</small></span>
        <button class="nav-logout" @click="onLogout">退出</button>
      </div>
    </nav>
    <main class="mgmt-main"><router-view /></main>
  </div>
</template>

<script setup>
import { useAuthStore } from '../stores/auth'
import { useRouter } from 'vue-router'
const auth = useAuthStore()
const router = useRouter()
async function onLogout() {
  await auth.logout()
  router.push('/login')
}
</script>

<style scoped>
.mgmt { min-height: 100vh; background: #0f172a; color: #e2e8f0; }
.topnav {
  display: flex; align-items: center; gap: 20px;
  padding: 0 20px; height: 52px;
  background: #1e293b; border-bottom: 1px solid #334155;
}
.nav-brand { font-weight: 600; color: #60a5fa; white-space: nowrap; }
.nav-links { display: flex; gap: 6px; flex: 1; flex-wrap: wrap; }
.nav-links a {
  padding: 6px 12px; border-radius: 6px; color: #cbd5e1;
  text-decoration: none; font-size: 14px;
}
.nav-links a:hover { background: #334155; color: #fff; }
.nav-links a.router-link-active { background: #3b82f6; color: #fff; }
.nav-user { display: flex; align-items: center; gap: 12px; }
.nav-dash { color: #60a5fa; text-decoration: none; font-size: 14px; }
.nav-name { font-size: 13px; }
.nav-name small { color: #94a3b8; }
.nav-logout {
  padding: 5px 12px; border: 1px solid #475569; border-radius: 6px;
  background: transparent; color: #e2e8f0; cursor: pointer; font-size: 13px;
}
.nav-logout:hover { background: #ef4444; border-color: #ef4444; }
.mgmt-main { padding: 20px; }
</style>
