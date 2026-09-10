# 04 - API 文档

所有 REST 接口前缀 `/api`，返回 JSON。鉴权基于 Flask 服务端 Session（cookie），无需 token。WebSocket 端点 `ws://localhost:8083/ws/dashboard`。

## 一、免登录接口（大屏用）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/overview` | 设备概览 + 在线率（total/online/offline/online_rate） |
| GET | `/api/device-status` | 8 通道实时值（扁平 key→value） |
| GET | `/api/alarm-stats` | 告警统计（各级别 + 各状态 + 今日 + active_critical） |
| GET | `/api/alarms/recent?limit=10` | 最近告警列表（limit 1~50） |
| GET | `/api/scene-rules` | 场景规则列表（含 trigger_count/last_triggered） |
| GET | `/api/history/<key>?minutes=30` | 某采集点历史时序（minutes 1~180） |
| POST | `/api/alarms/<id>/ack` | 确认单条告警（active→acknowledged） |
| POST | `/api/alarms/ack-all` | 一键确认所有 active 告警 |
| POST | `/api/alarms/clear-all` | 一键清除所有告警 |
| POST | `/api/devices/toggle` | 继电器控制（写库 + MQTT 下发 + WS 广播） |

`/api/devices/toggle` 请求体：

```json
{ "key": "relay1", "value": "1" }
```

`key` 限 `relay1`~`relay4`，`value` 限 `0`/`1`。

## 二、鉴权接口

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| POST | `/api/auth/login` | - | 登录，成功写 session cookie |
| POST | `/api/auth/logout` | - | 登出，清会话 |
| GET | `/api/auth/me` | - | 当前用户（未登录 user=null） |

`/api/auth/login` 请求体：

```json
{ "username": "admin", "password": "admin123" }
```

默认账号：`admin/admin123`（admin 角色）、`user/user123`（user 角色）。

## 三、管理接口

`[login]` = 需登录，`[admin]` = 需管理员。未登录返回 401 JSON，权限不足返回 403 JSON（不跳转，适配 SPA）。

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/api/stats` | login | 管理看板统计（映射/用户/在线/告警/概览） |
| GET | `/api/devices` | login | 设备控制台（继电器卡片 + 传感器卡片） |
| POST | `/api/devices/all` | admin | 一键全开/全关，body `{"action":"on"\|"off"}` |
| GET | `/api/mappings` | login | 映射列表（含禁用） |
| POST | `/api/mappings` | admin | 新增映射 |
| PUT | `/api/mappings/<id>` | admin | 更新映射 |
| DELETE | `/api/mappings/<id>` | admin | 删除映射 |
| POST | `/api/mappings/<id>/toggle` | admin | 启用/禁用切换 |
| GET | `/api/users` | admin | 用户列表 |
| POST | `/api/users` | admin | 新增用户 |
| PUT | `/api/users/<id>/role` | admin | 改角色 |
| PUT | `/api/users/<id>/password` | admin | 重置密码 |
| DELETE | `/api/users/<id>` | admin | 删除用户（不能删当前自己） |
| GET | `/api/sessions` | admin | 在线用户 + 最近 30 条登录历史 |
| GET | `/api/config-points` | login | 网关配置（非 admin 密码脱敏为 ******） |
| POST | `/api/config-points` | admin | 保存网关配置（写 firmware/config.json） |

映射新增/更新字段：`gateway_key`/`product_id`/`device_id`/`property_name`/`description`/`enabled`，全部正则校验。

## 四、WebSocket

端点：`ws://localhost:8083/ws/dashboard`（免登录）

连接后立即推送一份全量 `device_status` 快照，随后按事件推送。消息格式：

```json
{ "type": "device_status", "data": { ... }, "ts": 1715400000.0 }
```

| type | data | 触发 |
|------|------|------|
| `device_status` | 8 通道扁平值 | 状态变化（1.5s 节流） |
| `alarm_new` | 单条告警对象 | 新告警 id |
| `rule_triggered` | {id,name,action_type,trigger_count} | trigger_count 增长 |
| `relay_changed` | {key,value,published} | 大屏点击 toggle |
| `history_tick` | 4 传感器历史点数组 | 每 5s |
| `overview_tick` | 设备概览统计 | 每 5s |

## 五、错误响应格式

所有接口返回 `{ok: boolean, error?: string}` 结构。

| HTTP | 场景 | 示例 |
|------|------|------|
| 200 | 成功 | `{"ok": true, "total": 8, "online": 8, "online_rate": 100}` |
| 400 | 参数校验失败 | `{"ok": false, "error": "gateway_key 格式错误"}` |
| 401 | 未登录 | `{"ok": false, "error": "未登录"}` |
| 403 | 权限不足 | `{"ok": false, "error": "需要管理员权限"}` |
| 404 | 资源不存在 | `{"ok": false, "error": "映射不存在"}` |

## 六、核心端点响应示例

### GET /api/overview

```json
{
  "ok": true,
  "total": 8,
  "online": 8,
  "offline": 0,
  "online_rate": 100
}
```

### GET /api/device-status

```json
{
  "ok": true,
  "data": {
    "relay1": "1", "relay2": "0", "relay3": "1", "relay4": "0",
    "temperature": "26.5", "humidity": "58.0", "human": "0", "smoke": "12"
  }
}
```

### GET /api/alarm-stats

```json
{
  "ok": true,
  "by_level": {"info": 0, "warning": 0, "critical": 0},
  "by_status": {"active": 0, "acknowledged": 0, "cleared": 0},
  "today": 0,
  "active_critical": 0
}
```

### GET /api/scene-rules

```json
{
  "ok": true,
  "rules": [
    {
      "id": 1,
      "name": "高温自动断电",
      "trigger_key": "temperature",
      "trigger_operator": ">",
      "trigger_value": "35",
      "action_type": "all_relay_off",
      "alarm_level": "critical",
      "cooldown_sec": 60,
      "trigger_count": 15,
      "enabled": true,
      "last_triggered": "2026-09-10 07:45:00"
    }
  ]
}
```

### POST /api/devices/toggle

请求：
```json
{ "key": "relay1", "value": "0" }
```

响应：
```json
{
  "ok": true,
  "key": "relay1",
  "value": "0",
  "published": true,
  "msg": "继电器 relay1 已关闭，MQTT 下发成功"
}
```

`published=true` 表示 MQTT write 已发送（FakeBridge 模式下始终为 true，跳过 MQTT 实际发布）。

## 七、WebSocket 事件 data 结构

### device_status
```json
{
  "type": "device_status",
  "data": {
    "relay1": "1", "relay2": "0", ..., "smoke": "12"
  },
  "ts": 1725854400.123
}
```

### alarm_new
```json
{
  "type": "alarm_new",
  "data": {
    "id": 524,
    "level": "critical",
    "status": "active",
    "rule_name": "高温自动断电",
    "source_key": "temperature",
    "source_value": "37",
    "message": "规则「高温自动断电」触发: temperature=37, 已执行 全关继电器",
    "triggered_at": "2026-09-10 07:45:00"
  },
  "ts": 1725854400.456
}
```

### rule_triggered
```json
{
  "type": "rule_triggered",
  "data": {
    "id": 1,
    "name": "高温自动断电",
    "action_type": "all_relay_off",
    "trigger_count": 16
  },
  "ts": 1725854400.789
}
```

### relay_changed
```json
{
  "type": "relay_changed",
  "data": {
    "key": "relay1",
    "value": "0",
    "published": true
  },
  "ts": 1725854401.012
}
```

### history_tick / overview_tick — 定时推送
- history_tick：4 个传感器最近 30 个时序点数组（每 30s 写一个点）
- overview_tick：同 `/api/overview` 响应体

## 八、典型调用示例

```bash
# 概览
curl http://localhost:8083/api/overview

# 登录（保留 cookie）
curl -c cookies.txt -X POST http://localhost:8083/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}'

# 带 cookie 访问管理接口
curl -b cookies.txt http://localhost:8083/api/mappings
```

相关文档：[02-架构设计](02-architecture.md) ｜ [05-部署指南](05-deploy.md)
