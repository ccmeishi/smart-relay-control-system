import { defineStore } from 'pinia'
import http from '../api/http'

export const useAuthStore = defineStore('auth', {
  state: () => ({ user: null, loaded: false }),
  getters: {
    isLoggedIn: (s) => !!s.user,
    isAdmin: (s) => s.user?.role === 'admin',
  },
  actions: {
    async fetchMe() {
      try {
        const r = await http.me()
        this.user = r.user
      } catch {
        this.user = null
      }
      this.loaded = true
    },
    async login(username, password) {
      const r = await http.login(username, password)
      this.user = r.user
      this.loaded = true
      return r
    },
    async logout() {
      try { await http.logout() } catch {}
      this.user = null
    },
  },
})
