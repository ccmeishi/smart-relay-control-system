import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import Layout from '../components/Layout.vue'
import DashboardView from '../views/DashboardView.vue'
import LoginView from '../views/LoginView.vue'
import DevicesView from '../views/DevicesView.vue'
import MappingsView from '../views/MappingsView.vue'
import ScenesView from '../views/ScenesView.vue'
import UsersView from '../views/UsersView.vue'
import SessionsView from '../views/SessionsView.vue'
import ConfigView from '../views/ConfigView.vue'

const routes = [
  // 大屏 (免登录, 全屏, 无导航)
  { path: '/', name: 'dashboard', component: DashboardView },
  { path: '/login', name: 'login', component: LoginView },

  // 管理后台 (需登录, Layout 包裹导航)
  {
    path: '/manage',
    component: Layout,
    meta: { auth: true },
    children: [
      { path: '', redirect: '/manage/devices' },
      { path: 'devices', name: 'devices', component: DevicesView },
      { path: 'mappings', name: 'mappings', component: MappingsView },
      { path: 'scenes', name: 'scenes', component: ScenesView },
      { path: 'users', name: 'users', component: UsersView, meta: { admin: true } },
      { path: 'sessions', name: 'sessions', component: SessionsView, meta: { admin: true } },
      { path: 'config', name: 'config', component: ConfigView, meta: { admin: true } },
    ],
  },
  // 兜底
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

// 全局路由守卫: 管理页需登录, admin 页需 admin 角色
router.beforeEach(async (to) => {
  const auth = useAuthStore()
  if (!auth.loaded) {
    await auth.fetchMe()
  }
  if (to.meta.auth && !auth.isLoggedIn) {
    return { path: '/login', query: { redirect: to.fullPath } }
  }
  if (to.meta.admin && !auth.isAdmin) {
    return { path: '/manage/devices' }
  }
  return true
})

export default router
