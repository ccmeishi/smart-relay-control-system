import { defineStore } from 'pinia'
import api from '../api/http'

const HISTORY_KEYS = ['temperature', 'humidity', 'human', 'smoke']

export const useDashboardStore = defineStore('dashboard', {
  state: () => ({
    overview: { total: 0, online: 0, offline: 0, online_rate: 0 },
    deviceStatus: {},          // { relay1: '1', temperature: '28.5', ... }
    alarmStats: { total: 0, active: 0, acknowledged: 0, cleared: 0,
                  info: 0, warning: 0, critical: 0, active_critical: 0,
                  by_level: { info: 0, warning: 0, critical: 0 } },
    recentAlarms: [],
    sceneRules: [],
    history: { temperature: [], humidity: [], human: [], smoke: [] },
    wsConnected: false,
    flashRuleId: null,         // 刚触发的规则 id (卡片高亮)
    flashAlarmId: null         // 刚收到的告警 id (闪烁)
  }),

  actions: {
    // 首屏初始化: 拉全量 REST
    async initLoad() {
      try {
        const [ov, ds, stats, alarms, rules] = await Promise.all([
          api.overview(),
          api.deviceStatus(),
          api.alarmStats(),
          api.recentAlarms(10),
          api.sceneRules()
        ])
        this.overview = ov
        this.deviceStatus = ds
        this.alarmStats = stats
        this.recentAlarms = alarms
        this.sceneRules = rules
        // 拉历史趋势
        for (const k of HISTORY_KEYS) {
          try {
            this.history[k] = await api.history(k, 30)
          } catch (e) { /* 忽略单个指标失败 */ }
        }
      } catch (e) {
        console.error('[store] init load failed', e)
      }
    },

    // 周期轮询兜底 (WS 之外的保险)
    async pollOverview() {
      try { this.overview = await api.overview() } catch (e) {}
    },
    async pollAlarmStats() {
      try {
        this.alarmStats = await api.alarmStats()
      } catch (e) {}
    },
    async pollSceneRules() {
      try { this.sceneRules = await api.sceneRules() } catch (e) {}
    },

    // 继电器切换
    async toggleRelay(key) {
      const cur = this.deviceStatus[key] === '1' || this.deviceStatus[key] === 1
      const newVal = cur ? '0' : '1'
      try {
        await api.toggleRelay(key, newVal)
        // 乐观更新 (WS relay_changed 会校正)
        this.deviceStatus[key] = newVal
      } catch (e) {
        console.error('[store] toggle failed', e)
      }
    },

    // WS 事件分发
    applyEvent(ev) {
      switch (ev.type) {
        case 'device_status':
          this.deviceStatus = ev.data
          break
        case 'overview_tick':
          this.overview = ev.data
          break
        case 'alarm_new':
          this.recentAlarms.unshift(ev.data)
          if (this.recentAlarms.length > 20) this.recentAlarms.pop()
          this.flashAlarmId = ev.data.id
          this.alarmStats = { ...this.alarmStats }
          // 统计 +1 (简单本地递增, 下次轮询校正)
          this.pollAlarmStats()
          setTimeout(() => { this.flashAlarmId = null }, 3000)
          break
        case 'rule_triggered': {
          const r = this.sceneRules.find((x) => x.id === ev.data.id)
          if (r) r.trigger_count = ev.data.trigger_count
          this.flashRuleId = ev.data.id
          setTimeout(() => { this.flashRuleId = null }, 1000)
          break
        }
        case 'relay_changed':
          if (ev.data && ev.data.key) {
            this.deviceStatus[ev.data.key] = ev.data.value
          }
          break
        case 'history_tick':
          if (ev.data) {
            for (const k of HISTORY_KEYS) {
              if (ev.data[k]) this.history[k] = ev.data[k]
            }
          }
          break
      }
    }
  }
})
