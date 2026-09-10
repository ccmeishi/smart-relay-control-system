import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 8000, withCredentials: true })

// 响应拦截: 直接返回 r.data; 401 时管理页跳登录 (大屏接口不会 401)
http.interceptors.response.use(
  (r) => r.data,
  (e) => {
    if (e.response?.status === 401 && location.pathname.startsWith('/manage')) {
      location.href = '/login'
    }
    return Promise.reject(e)
  }
)

export default {
  // ===== 大屏 (免登录) =====
  overview: () => http.get('/overview'),
  deviceStatus: () => http.get('/device-status'),
  alarmStats: () => http.get('/alarm-stats'),
  recentAlarms: (limit = 10) => http.get(`/alarms/recent?limit=${limit}`),
  sceneRules: () => http.get('/scene-rules'),
  history: (key, minutes = 30) => http.get(`/history/${key}?minutes=${minutes}`),
  ackAlarm: (id) => http.post(`/alarms/${id}/ack`),
  ackAllAlarms: () => http.post('/alarms/ack-all'),
  clearAllAlarms: () => http.post('/alarms/clear-all'),
  toggleRelay: (key, value) => http.post('/devices/toggle', { key, value }),

  // ===== 鉴权 =====
  me: () => http.get('/auth/me'),
  login: (username, password) => http.post('/auth/login', { username, password }),
  logout: () => http.post('/auth/logout'),

  // ===== 管理后台 =====
  stats: () => http.get('/stats'),
  devices: () => http.get('/devices'),
  devicesAll: (action) => http.post('/devices/all', { action }),
  mappings: () => http.get('/mappings'),
  addMapping: (m) => http.post('/mappings', m),
  updateMapping: (id, m) => http.put(`/mappings/${id}`, m),
  deleteMapping: (id) => http.delete(`/mappings/${id}`),
  toggleMapping: (id) => http.post(`/mappings/${id}/toggle`),
  users: () => http.get('/users'),
  addUser: (u) => http.post('/users', u),
  updateUserRole: (id, role) => http.put(`/users/${id}/role`, { role }),
  resetPassword: (id, password) => http.put(`/users/${id}/password`, { password }),
  deleteUser: (id) => http.delete(`/users/${id}`),
  sessions: () => http.get('/sessions'),
  configPoints: () => http.get('/config-points'),
  saveConfig: (c) => http.post('/config-points', c),
}
