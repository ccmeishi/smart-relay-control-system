import axios from 'axios'

const http = axios.create({ baseURL: '/api', timeout: 8000 })

http.interceptors.response.use(
  (r) => r.data,
  (e) => {
    console.error('[http]', e.config?.url, e.message)
    return Promise.reject(e)
  }
)

export default {
  overview: () => http.get('/overview'),
  deviceStatus: () => http.get('/device-status'),
  alarmStats: () => http.get('/alarm-stats'),
  recentAlarms: (limit = 10) => http.get(`/alarms/recent?limit=${limit}`),
  sceneRules: () => http.get('/scene-rules'),
  history: (key, minutes = 30) => http.get(`/history/${key}?minutes=${minutes}`),
  toggleRelay: (key, value) => http.post('/devices/toggle', { key, value })
}
