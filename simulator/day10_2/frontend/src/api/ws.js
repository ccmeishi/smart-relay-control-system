// WebSocket 客户端: 自动重连 (指数退避 1s→2s→4s... 上限 30s)
export class WsClient {
  constructor(onEvent, onStatusChange) {
    this.onEvent = onEvent
    this.onStatusChange = onStatusChange || (() => {})
    this.ws = null
    this.retry = 0
    this.shouldRun = true
    // 开发模式走 vite 代理 (相对路径 /ws), 生产模式同源
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    this.url = `${proto}://${location.host}/ws/dashboard`
  }

  connect() {
    try {
      this.ws = new WebSocket(this.url)
    } catch (e) {
      this._scheduleReconnect()
      return
    }

    this.ws.onopen = () => {
      this.retry = 0
      console.log('[ws] connected')
      this.onStatusChange(true)
    }

    this.ws.onmessage = (e) => {
      try {
        this.onEvent(JSON.parse(e.data))
      } catch (err) {
        console.error('[ws] parse error', err)
      }
    }

    this.ws.onclose = () => {
      this.onStatusChange(false)
      if (!this.shouldRun) return
      this._scheduleReconnect()
    }

    this.ws.onerror = () => {
      // close 会随后触发, 统一在 onclose 重连
    }
  }

  _scheduleReconnect() {
    const delay = Math.min(30000, 1000 * Math.pow(2, this.retry++))
    console.log(`[ws] reconnect in ${delay}ms`)
    setTimeout(() => {
      if (this.shouldRun) this.connect()
    }, delay)
  }

  close() {
    this.shouldRun = false
    try { this.ws && this.ws.close() } catch (e) {}
  }
}
