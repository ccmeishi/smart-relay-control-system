# Day10 — 场景联动与告警机制

> 在 Day9 动态映射 + Web 管理后台的基础上，新增**场景规则引擎**和**告警三态流转**，让平台从「被动展示」升级为「主动联动 + 主动告警」。

---

## 一、本日目标

| 目标 | 说明 |
|------|------|
| 场景联动 | 当采集点值满足条件时，自动执行设备控制动作（如温度过高→全关继电器） |
| 告警机制 | 规则触发或手动产生告警记录，支持「未确认→已确认→已清除」三态流转 |
| Web 管理 | 场景规则 CRUD + 告警列表查看/确认/清除/批量操作 |
| 看板统计 | 看板新增「未确认告警数」「场景规则数」两张统计卡片 + 告警环形图 |

---

## 二、架构图

```
ESP32-C3 网关 (relay-cc/relaycc)
    │ MQTT 上报 (温度/湿度/人体/烟雾/继电器)
    ▼
Python Bridge gateway_bridge.py
    │ 1. 按路由表拆分转发到 7 个虚拟设备 (Day9 已有)
    │ 2. 【新增】评估场景规则 evaluate_scene_rules()
    │ 3. 【新增】命中规则 → 执行动作 (set_relay/all_relay_off/send_alarm)
    │ 4. 【新增】产生告警记录 create_alarm() + MQTT 通知
    ▼
SQLite db/iot_platform.db
    ├── device_mappings  (Day9 已有, 8 条路由)
    ├── users            (Day9 已有, admin/user)
    ├── login_sessions   (Day9 已有, 登录会话)
    ├── device_status    (Day9 已有, 实物状态缓存)
    ├── scene_rules      【新增】4 条预填充场景规则
    └── alarm_records    【新增】告警历史记录

Flask Web 127.0.0.1:8081
    ├── /dashboard   看板 (新增告警/场景统计卡片)
    ├── /scenes      【新增】场景规则管理 (CRUD)
    ├── /alarms      【新增】告警记录管理 (查看/确认/清除)
    ├── /devices     实物控制台 (Day9 已有)
    ├── /mappings    映射管理 (Day9 已有)
    ├── /config-points 采集点配置 (Day9 已有)
    ├── /sessions    在线用户 (Day9 已有)
    └── /users       用户管理 (Day9 已有)
```

---

## 三、代码结构

```
simulator/day10/
├── db.py                    ⭐ 数据层 (6 张表, 含场景规则评估引擎)
├── gateway_bridge.py        ⭐ Bridge (新增场景评估 + 动作执行 + 告警产生)
├── start_all.bat            一键启动 (Modbus + Bridge + Web)
├── requirements.txt         依赖
├── modbus_slave_sim.py      Modbus 从站模拟器 (与 Day9 一致)
├── set_modbus.py             Modbus 寄存器写入工具
├── detect_com.py            串口检测工具
├── esp32_firmware/          ESP32 固件 (与 Day9 一致)
│   ├── config.json          MQTT/WiFi/Modbus 配置
│   ├── main.py              双模式入口
│   ├── app_config.py        配置读写
│   ├── ap_config.py         AP 配网
│   ├── modbus_gw.py         Modbus 采集
│   ├── relay_hw.py          GPIO 抽象
│   ├── boot.py              极简启动
│   └── umqtt/simple.py      MQTT 客户端
├── web/
│   ├── app.py               ⭐ Flask 主应用 (新增 /scenes /alarms 路由)
│   └── templates/
│       ├── base.html        ⭐ 深色主题基类 (新增告警角标轮询)
│       ├── dashboard.html   ⭐ 看板 (新增告警/场景统计)
│       ├── scenes.html      【新增】场景规则管理
│       ├── alarms.html      【新增】告警记录管理
│       ├── mappings.html    映射管理
│       ├── devices.html     实物控制台
│       ├── config_points.html 采集点配置
│       ├── users.html       用户管理
│       ├── sessions.html    在线用户
│       └── login.html       登录页
└── db/                      SQLite 数据库 (自动生成)
    └── iot_platform.db
```

---

## 四、数据库设计

### 4.1 scene_rules 表（场景规则）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| name | TEXT | 规则名称（如「高温自动断电」） |
| description | TEXT | 描述 |
| trigger_key | TEXT | 触发采集点（temperature/human/smoke...） |
| trigger_operator | TEXT | 运算符（> < >= <= == !=） |
| trigger_value | TEXT | 阈值（字符串存储，比较时转 float） |
| action_type | TEXT | 动作类型（set_relay/all_relay_off/all_relay_on/send_alarm） |
| action_target | TEXT | 动作目标（set_relay 时为 relay1/relay2...） |
| action_value | TEXT | 动作值（set_relay 时为 0/1） |
| alarm_level | TEXT | 告警级别（info/warning/critical） |
| enabled | INTEGER | 是否启用（1/0） |
| cooldown_sec | INTEGER | 冷却时间（秒，避免频繁触发） |
| last_triggered | TIMESTAMP | 上次触发时间 |
| trigger_count | INTEGER | 累计触发次数 |

### 4.2 alarm_records 表（告警记录）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| rule_id | INTEGER | 关联规则 ID（NULL=手动产生） |
| rule_name | TEXT | 规则名称快照 |
| source_key | TEXT | 触发的采集点 |
| source_value | TEXT | 触发时的值 |
| level | TEXT | 告警级别（info/warning/critical） |
| message | TEXT | 告警描述 |
| status | TEXT | 状态（active/acknowledged/cleared） |
| triggered_at | TIMESTAMP | 触发时间 |
| acknowledged_at | TIMESTAMP | 确认时间 |
| acknowledged_by | TEXT | 确认人 username |

### 4.3 预填充的 4 条示例规则

| # | 名称 | 条件 | 动作 | 告警级别 | 冷却 |
|---|------|------|------|----------|------|
| 1 | 高温自动断电 | temperature > 35 | all_relay_off | critical | 60s |
| 2 | 烟雾告警联动 | smoke > 50 | all_relay_off | critical | 30s |
| 3 | 有人自动开灯 | human == 1 | set_relay(relay2, 1) | info | 10s |
| 4 | 无人自动关灯 | human == 0 | set_relay(relay2, 0) | info | 10s |

---

## 五、运行步骤

### 5.1 一键启动（推荐）

```bat
cd simulator\day10
start_all.bat
```

脚本会自动：
1. 检测 Python 和依赖库
2. 检测 5502/8081 端口冲突
3. 初始化 SQLite 数据库
4. 启动 Modbus 模拟器（端口 5502，unit_id=7）
5. 启动 Bridge（含场景评估，热重载）
6. 启动 Web 管理后台（端口 8081）

### 5.2 手动启动（分步）

```bat
cd simulator\day10

:: 1. 初始化数据库
python db.py

:: 2. 启动 Modbus 从站模拟器
python modbus_slave_sim.py 5502 7

:: 3. 启动 Bridge（新终端）
python gateway_bridge.py --hot-reload

:: 4. 启动 Web 后台（新终端）
python web\app.py
```

### 5.3 访问

- Web 后台：http://127.0.0.1:8081
- 默认账号：`admin / admin123`（管理员）或 `user / user123`（普通用户）

### 5.4 验证场景联动

打开两个终端：

**终端 1：设置高温触发规则**
```bat
python set_modbus.py 36 60 1 50
```
（温度=36°C → 命中「高温自动断电」规则 → Bridge 自动全关继电器 + 产生 critical 告警）

**终端 2：查看 Web 看板**
- 浏览器打开 http://127.0.0.1:8081/alarms
- 看到 critical 级别告警记录
- 点击「确认」→ 状态变为「已确认」
- 点击「清除」→ 状态变为「已清除」

### 5.5 测试告警链路

在 Web 后台 http://127.0.0.1:8081/alarms 页面：
1. 点击「测试告警」按钮
2. 选择级别（info/warning/critical）
3. 输入消息
4. 提交后告警记录出现在列表
5. 测试「确认」「清除」「全部确认」「全部清除」

---

## 六、路由表

| URL | 方法 | 权限 | 功能 |
|-----|------|------|------|
| /login | GET/POST | 公开 | 登录 |
| /logout | GET | 公开 | 登出 |
| /dashboard | GET | login | 看板（含告警/场景统计） |
| /scenes | GET | login | 场景规则列表 |
| /scenes/add | POST | admin | 新增规则 |
| /scenes/\<id\>/edit | POST | admin | 编辑规则 |
| /scenes/\<id\>/delete | POST | admin | 删除规则 |
| /scenes/\<id\>/toggle | POST | admin | 启用/禁用规则 |
| /alarms | GET | login | 告警列表（支持 status/level 筛选） |
| /alarms/\<id\>/ack | POST | admin | 确认告警 |
| /alarms/\<id\>/clear | POST | admin | 清除告警 |
| /alarms/ack-all | POST | admin | 批量确认 |
| /alarms/clear-all | POST | admin | 批量清除 |
| /alarms/test | POST | admin | 手动产生测试告警 |
| /devices | GET | login | 实物控制台 |
| /devices/toggle | POST | admin | 继电器开关 |
| /devices/all | POST | admin | 全开/全关 |
| /mappings | GET | login | 映射管理 |
| /config-points | GET | login | 采集点配置 |
| /sessions | GET | admin | 在线用户 |
| /users | GET | admin | 用户管理 |
| /api/alarm-stats | GET | login | 告警统计（前端轮询） |
| /api/device-status | GET | login | 设备状态（前端轮询） |
| /api/routing | GET | login | 路由表 |

---

## 七、场景规则执行流程

```
1. ESP32 上报 properties/report (含 temperature=36)
        │
2. Bridge handle_gateway_properties_report()
        │
   ├── update_device_status('temperature', 36)   # 更新缓存
        │
   ├── evaluate_scene_rules('temperature', 36)     # 【新增】评估规则
        │   │
        │   ├── 查询 scene_rules WHERE enabled=1 AND trigger_key='temperature'
        │   ├── 检查冷却 (last_triggered + cooldown_sec)
        │   ├── _compare(36, '>', 35) → True → 命中规则1
        │   └── 返回 [{rule_id:1, action_type:'all_relay_off', alarm_level:'critical', ...}]
        │
3. execute_scene_actions(actions)                  # 【新增】执行动作
        │
   ├── 动作: all_relay_off → 构造 {relay1:0, relay2:0, relay3:0, relay4:0}
   ├── 向网关发 properties/write (MQTT publish)
   │
   └── create_alarm(rule_id=1, rule_name='高温自动断电',
                     source_key='temperature', source_value='36',
                     level='critical', message='...')
        │
4. alarm_records 表新增一条记录 (status='active')
        │
5. Bridge 向 /system/alarm/notify 发布 MQTT 告警通知
        │
6. Web 前端每 30 秒轮询 /api/alarm-stats
   → 看板角标显示未确认告警数 → 用户点击 /alarms 查看
```

---

## 八、告警三态流转

```
┌─────────┐  admin 确认  ┌──────────────┐  admin 清除  ┌──────────┐
│ active  │ ──────────→ │ acknowledged │ ──────────→ │ cleared  │
│ (未确认) │             │  (已确认)    │             │ (已清除)  │
└─────────┘             └──────────────┘             └──────────┘
     │                                                   ▲
     └──────────────── admin 直接清除 ──────────────────┘
```

- **active（未确认）**：新产生的告警，需管理员关注
- **acknowledged（已确认）**：管理员已知悉，待后续清除
- **cleared（已清除）**：已处理完毕，归档保留

---

## 九、权限矩阵

| 功能 | admin | user |
|------|-------|------|
| 查看场景规则 | ✅ | ✅ |
| 新增/编辑/删除规则 | ✅ | ❌ |
| 启用/禁用规则 | ✅ | ❌ |
| 查看告警列表 | ✅ | ✅ |
| 确认/清除告警 | ✅ | ❌ |
| 批量确认/清除 | ✅ | ❌ |
| 手动测试告警 | ✅ | ❌ |
| 看板告警统计 | ✅ | ✅ |

---

## 十、文件功能详解

### 10.1 db.py — 数据层 + 规则引擎

| 函数 | 功能 |
|------|------|
| `init_db(force)` | 建表 + 预填充（8 路由 + 2 用户 + 4 规则） |
| `load_gateway_config()` | 从 config.json 读 MQTT/WiFi 配置 |
| `evaluate_scene_rules(gateway_key, value)` | **核心**：评估采集点变化，返回需执行的动作列表 |
| `execute_scene_actions(actions)` | 在 Bridge 中执行，此处仅 db.py 不含 |
| `create_alarm(...)` | 产生告警记录 |
| `list_alarms(status, level)` | 查询告警（支持过滤） |
| `acknowledge_alarm(id, username)` | 确认告警（active→acknowledged） |
| `clear_alarm(id)` | 清除告警（→cleared） |
| `get_alarm_stats()` | 告警统计（各级别/各状态数量） |
| `get_scene_rule_stats()` | 场景规则统计（启用/禁用/触发次数） |

### 10.2 gateway_bridge.py — Bridge

新增关键函数：
- `execute_scene_actions(actions)`：执行规则动作（发 MQTT write + 产生告警）
- 在 `handle_gateway_properties_report()` 中新增：上报每个 key 后调用 `evaluate_scene_rules()`

### 10.3 web/app.py — Flask

新增 11 个路由：
- `/scenes` + 4 个 CRUD 路由
- `/alarms` + 5 个管理路由（查看/确认/清除/批量/测试）
- `/api/alarm-stats`（前端轮询）

---

## 十一、常见问题排查

| 问题 | 原因 | 解决 |
|------|------|------|
| 场景规则不触发 | Bridge 未用 `--hot-reload` 或规则被禁用 | 用 `start_all.bat` 启动，检查规则 enabled=1 |
| 告警重复产生 | 冷却时间太短 | 编辑规则增大 `cooldown_sec` |
| 告警角标不更新 | 前端轮询间隔 30 秒 | 等 30 秒或刷新页面 |
| 温度规则不触发 | set_modbus 写入的是 ×10 值 | `set_modbus.py 36` 写入 36（=3.6°C），需写 360 才是 36°C |
| 实物测试无数据 | Modbus 模拟器未启动或端口占用 | 检查 5502 端口，重启 modbus_slave_sim.py |
| Web 页面打不开 | 8081 端口被占 | 关闭旧 Web 进程或改 `WEB_PORT` 环境变量 |

---

## 十二、验收清单

- [ ] `python db.py` 初始化成功，显示 4 条场景规则
- [ ] `start_all.bat` 一键启动 3 个进程
- [ ] Web 后台 http://127.0.0.1:8081 可访问
- [ ] 登录 admin/admin123
- [ ] 看板显示 8 张统计卡片（含场景规则/未确认告警）
- [ ] /scenes 页面显示 4 条预填充规则
- [ ] /alarms 页面显示告警列表（初始为空）
- [ ] 点击「测试告警」→ 产生一条告警记录
- [ ] 告警角标显示未确认数（红色脉冲）
- [ ] 确认告警 → 状态变为「已确认」
- [ ] 清除告警 → 状态变为「已清除」
- [ ] `python set_modbus.py 360 600 1 50` → 温度=36°C → 命中「高温自动断电」规则
- [ ] Bridge 终端显示场景规则命中日志
- [ ] /alarms 页面出现 critical 告警记录
