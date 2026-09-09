# Day9 · SQLite 动态路由 + Web 管理后台 + 权限系统 + 实物控制台

## 当天目标

Day8 时，Bridge 里的**路由表是硬编码的**（`gateway_bridge.py` 里写死 8 条 `UP_ROUTING` 字典）。每新增一个虚拟设备都要改 Python 代码 + 重启 Bridge。

Day9 一口气解决 4 个问题：

1. **路由表 SQLite 动态化**：Bridge 启动时从 `db/iot_platform.db` 加载，加 `--hot-reload` 每 5 秒自动刷新，**零代码改动增删虚拟设备**
2. **深色主题 Web 管理后台**（Flask）：8 个页面——看板、映射管理、实物控制台、采集点配置、用户管理、在线用户、登录/退出
3. **完整权限系统**：admin（增删改查全部）/ user（只读），后端装饰器拦截 + 前端隐藏按钮 + db 层源头校验
4. **实物控制台**：通过 MQTT 直接下发继电器开关命令到 ESP32 网关，实时显示 device_status 缓存

## Day8 → Day9 改了什么

| 对比项 | Day8 | Day9 |
|--------|------|------|
| 路由表存储 | Python 源码硬编码 `UP_ROUTING = {...}` | SQLite `db/iot_platform.db` 的 `device_mappings` 表 |
| 新增映射 | 改代码 + 重启 Bridge | Web 页面点新增 → Bridge 热刷新生效 |
| Bridge 刷新 | 改完必须手动重启 | 默认启动加载一次；`--hot-reload` 每 5 秒自动刷 |
| 用户系统 | 无 | SQLite `users` 表，区分 admin/user，**db 层源头校验** |
| 管理界面 | 无 | Flask Web（深色主题），8 个页面 |
| 实物控制台 | 无 | **MQTT 直连下发继电器命令**，device_status 实时缓存 |
| 在线追踪 | 无 | `login_sessions` 表 + 5 分钟超时自动判定离线 + 同一用户新登录踢旧 session |
| 采集点管理 | 无 | Web 页面编辑 `esp32_firmware/config.json` 并下载回板子 |
| 敏感信息 | 无保护 | 普通用户看原始 JSON 时密码脱敏（`wifi_pass`/`mqtt_pass` → `******`） |
| MQTT 凭据 | 三处硬编码 | **统一从 `config.json` 读取**（db.py `load_gateway_config()`） |
| 运行依赖 | `paho-mqtt` | `paho-mqtt` + `flask` |

## 架构

```
┌──────────────┐  Modbus TCP   ┌──────────────────────┐
│ Modbus 模拟器 │ ←读 reg0/1/4/5→│   ESP32-C3 网关       │
│ (温湿度/人体/ │              │   (产品 relay-cc      │
│  烟雾)        │              │    设备 relaycc)      │
│ 192.168.20.59 │              │                      │
│   :5502       │              │  4路GPIO继电器        │
└──────────────┘              │  + Modbus采集         │
                              └──────────┬───────────┘
                                         │ MQTT 上报 + 接收下行命令
                                         ▼
                              ┌──────────────────────┐
                              │  Python Bridge        │
                              │  gateway_bridge.py    │
                              │                      │
                              │  ① 路由表 ← SQLite    │
                              │  ② 订阅 + 转发上行    │
                              │  ③ 订阅 + 回流下行    │
                              │  ④ 写入 device_status │ ← 实物状态缓存
                              └──────────┬───────────┘
                                         │
                                         ▼
                              JetLinks 平台 (6 产品 / 7 虚拟设备)

  ┌─────────────────────────────────────────────────────────────────────┐
  │  Day9 新增: Web 管理后台 (Flask, http://127.0.0.1:8081)              │
  │                                                                     │
  │   Flask app.py                                                      │
  │   ┌─────────────────────────────────────────────────────────────┐   │
  │   │   看板 /dashboard  实物控制台 /devices  在线用户 /sessions   │   │
  │   │   采集点配置 /config-points  映射管理 /mappings             │   │
  │   │   用户管理 /users (仅 admin)  登录/退出                     │   │
  │   └─────────────────────────────────────────────────────────────┘   │
  │              │                               │                     │
  │              ▼                               ▼                     │
  │      SQLite db.py 数据层            MQTT 直连 (Web 也能下发)        │
  │      ┌──────────────────────┐      ┌─────────────────────────┐     │
  │      │ device_mappings      │      │ relay-cc/relaycc/       │     │
  │      │ users                │      │ properties/write       │     │
  │      │ login_sessions       │      │ → 直接控继电器           │     │
  │      │ device_status        │      └─────────────────────────┘     │
  │      └──────────────────────┘                                     │
  └─────────────────────────────────────────────────────────────────────┘
```

## 数据库设计（SQLite）

数据库文件：`day9/db/iot_platform.db`（首次运行 `python db.py` 自动创建）

### 四张核心表

**device_mappings 表 — 设备映射关系**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| gateway_key | TEXT UNIQUE | 网关侧采集点 key：relay1, temperature, human... |
| product_id | TEXT | 虚拟产品 ID：lock-cc, sensor-cc... |
| device_id | TEXT | 虚拟设备 ID：lock001, sensorcc... |
| property_name | TEXT | 虚拟属性名：switch, temperature, detected... |
| description | TEXT | 备注说明 |
| enabled | INTEGER | 1=启用（参与路由）、0=禁用 |
| created_at / updated_at | TIMESTAMP | 创建/更新时间 |

**users 表 — 用户账号（SHA-256 哈希，无明文密码）**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| username | TEXT UNIQUE | 登录名（`^[a-zA-Z0-9_]{3,20}$`） |
| password_hash | TEXT | SHA-256 哈希（64 字符 hex） |
| role | TEXT | `admin` / `user`（**只有这两个值**，非法会被 db 层拒绝） |
| display_name | TEXT | 显示名（可选） |
| created_at | TIMESTAMP | 创建时间 |

**login_sessions 表 — 在线追踪（Day9 新增）**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| user_id | INTEGER FK | 关联 users.id |
| username | TEXT | 冗余存用户名（方便列表查询） |
| ip | TEXT | 登录 IP（127.0.0.1 / 真实 IP） |
| login_at | TIMESTAMP | 登录时间 |
| logout_at | TIMESTAMP | 退出时间（正常登出） |
| last_seen | TIMESTAMP | **最后活跃心跳**（每次请求自动 touch） |
| status | TEXT | `online` / `offline` |

> **超时判定**：`list_online_users()` 和 `get_online_count()` 加了 `last_seen > datetime('now', '-5 minutes')` 过滤。关浏览器 5 分钟后自动视为离线。**同一用户新登录时自动踢掉之前的 online session**（保留历史但只有最新一条 online）。

**device_status 表 — 实物最新状态缓存（Day9 新增）**

| 字段 | 类型 | 说明 |
|------|------|------|
| gateway_key | TEXT PK | relay1, temperature, human... |
| value | TEXT | Bridge 收到网关上报时同步写入最新值（JSON） |
| updated_at | TIMESTAMP | Bridge 上次更新时间 |

> 实物控制台 `/devices` 就是查这张表——Bridge 每次收到 `relay-cc/relaycc/properties/report` 都会同步更新 8 条记录。

### 输入校验正则（db.py 顶部，源头防御）

| 正则 | 应用于 | 规则 |
|------|--------|------|
| `_RE_USER = ^[a-zA-Z0-9_]{3,20}$` | 用户名 | 仅字母/数字/下划线，3~20 位 |
| `_RE_PASS = ^[\x20-\x7e]{6,64}$` | 密码 | 可打印 ASCII，6~64 位 |
| `_RE_NAME = ^[a-zA-Z0-9_\-\u4e00-\u9fff]{0,30}$` | 显示名 | 中英文/数字/下划线，可选 |
| role 白名单 | admin / user | db 层拒绝 `superadmin` 等非法角色 |

> **为什么放 db 层不放路由层？** Flask 路由层的校验可以被绕过（直接调 `from db import add_user; add_user('bad user!', '123', 'superadmin')`）。db 层校验是**最后一道防线**，任何调用方式都拦。

### 预填充数据

首次运行自动插入：

**8 条映射**（与 Day8 硬编码完全一致，向后兼容）：

| gateway_key | product_id | device_id | property_name |
|-------------|------------|-----------|---------------|
| relay1 | lock-cc | lock001 | switch |
| relay2 | light-cc | light001 | switch |
| relay3 | light-cc | light002 | switch |
| relay4 | ac-cc | ac001 | switch |
| temperature | sensor-cc | sensorcc | temperature |
| humidity | sensor-cc | sensorcc | humidity |
| human | human-cc | human001 | detected |
| smoke | smoke-cc | smoke001 | level |

**2 个默认用户**：
- `admin / admin123` — 管理员
- `user / user123` — 普通用户

## 代码结构（day9 文件夹里有什么）

```
day9/
├── README.md                 ← 本文档
├── requirements.txt          ← Python 依赖 (paho-mqtt, flask)
│
├── db.py                     ← ⭐ SQLite 数据层 (Bridge 和 Web 共用)
│   ├── load_gateway_config()   统一从 esp32_firmware/config.json 读 MQTT/WiFi 凭据
│   ├── init_db()               建 4 张表 + 预填充 8 条路由 + 2 个用户
│   ├── load_routing()          加载启用的路由表 → dict (Bridge 用)
│   ├── load_all_mappings()     加载所有映射含禁用 (Web 管理页用)
│   ├── add_mapping() / update_mapping() / delete_mapping()
│   ├── authenticate()          登录验证 (SHA-256 比对)
│   ├── add_user()              ⚠️ 内部已加 _RE_USER/_RE_PASS/role 校验
│   ├── update_user_role()      ⚠️ 内部已加 role 白名单校验
│   ├── reset_password()        ⚠️ 内部已加 _RE_PASS 校验
│   ├── kick_user_sessions()    同一用户新登录时踢掉旧 online session
│   ├── start_session() / end_session() / touch_session()  会话管理
│   ├── list_online_users()     带 5 分钟超时过滤 + 顺便清理 stale session
│   ├── get_online_count()      带 5 分钟超时过滤
│   ├── update_device_status()  Bridge 收到上报时写入缓存
│   ├── get_device_status_all() Web 实物控制台读取全部缓存
│   └── _RE_USER / _RE_PASS / _RE_NAME / _validate()    正则 + 统一校验入口
│
├── gateway_bridge.py         ← ⭐ Day9 Bridge (从 SQLite 加载路由)
│   ├── ⚠️ MQTT 凭据统一改从 load_gateway_config() 读取, 不再硬编码
│   ├── refresh_routing()       从 SQLite 重新加载, 支持 --hot-reload
│   ├── --hot-reload            命令行参数: 每 5 秒自动刷新
│   ├── 收到网关上报时 → update_device_status() 写缓存
│   └── 其他 MQTT 收发逻辑        与 Day8 一致
│
├── modbus_slave_sim.py       ← Modbus 从站模拟器 (从 Day8 复制)
├── set_modbus.py             ← 写传感器值工具 (从 Day8 复制)
├── detect_com.py             ← COM 口检测工具
│
├── start_all.bat             ← ⭐ 一键启动全部 (模拟器 + Bridge + Web)
│   ├── 先检查端口 5502/8081 冲突
│   ├── python db.py             首次建库
│   ├── start ModbusSim          cmd (5502, unit_id=7)
│   ├── start Bridge + hot-reload  cmd (MQTT)
│   └── start Web                cmd (8081)
│
├── start_web.bat             ← 只启动 Web 管理后台 (8081)
│
├── db/
│   └── iot_platform.db       ← SQLite 数据库 (首次运行自动创建)
│
├── web/
│   ├── app.py                ← ⭐ Flask 主应用 (所有路由 + 鉴权 + MQTT 下发)
│   │   ├── @login_required     已登录即可
│   │   ├── @admin_required     必须 admin 角色
│   │   ├── 登录时 kick_user_sessions() 踢旧 session
│   │   ├── before_request touch_session() 心跳维护 last_seen
│   │   └── /devices 实物控制台 → MQTT 下发 relay1/relay2/relay3/relay4
│   │
│   └── templates/            ← HTML 模板 (深色主题, 纯静态 CSS, base.html 统一样式)
│       ├── base.html           侧边栏 + 顶栏 + 深色主题 CSS 变量 + SVG 图标
│       ├── login.html          登录页 (用户名 + 密码)
│       ├── dashboard.html      ⭐ 看板 (7 张可点击 stat-card + 3 个图表区域)
│       ├── mappings.html       映射管理 (表格 + 新增/编辑弹窗, 仅 admin 可编辑)
│       ├── devices.html        ⭐ 实物控制台 (4 路继电器开关 + 传感器读数 + MQTT 直连)
│       ├── sessions.html      ⭐ 在线用户追踪 (在线列表 + 最近历史)
│       ├── config_points.html  ⭐ 采集点配置 (WiFi/MQTT/Modbus 可视化表单 + 原始JSON)
│       └── users.html          用户管理 (仅 admin: 增/改角色/重置密码/删除)
│
└── esp32_firmware/           ← Day8 ESP32 固件副本 (不变)
    ├── boot.py / main.py / ap_config.py / modbus_gw.py / relay_hw.py / app_config.py
    ├── config.json           当前配置: 192.168.20.59:5502 unit_id=7
    ├── umqtt/simple.py       MQTT 客户端库
    └── _firmware/ESP32_GENERIC_C3-v1.29.0.bin
```

## 每个代码文件是干什么的（新手逐个看）

### Python 后端（day9/ 根目录）

| 文件 | 干什么 | 什么时候碰 |
|------|--------|-----------|
| **db.py** | ⭐ **Day9 核心**。SQLite 数据层，Bridge 和 Web 都用它。4 张表的 CRUD + 正则校验 + MQTT 凭据统一读取。**不要手改这个文件** | 跑 `python db.py` 首次建库即可 |
| **gateway_bridge.py** | Day9 Bridge：订阅网关上报，按 SQLite 路由表拆分转发到 7 个虚拟设备；同时回流下行控制；写入 device_status 缓存。MQTT 凭据不再硬编码，从 `db.load_gateway_config()` 读 | `python gateway_bridge.py --hot-reload` 启动 |
| **modbus_slave_sim.py** | Modbus 从站模拟器（温湿度/人体/烟雾），与 Day8 完全相同 | `python modbus_slave_sim.py 5502 7` 启动 |
| **set_modbus.py** | 手动改模拟器里的传感器基准值 | 想改温度基准时跑 |
| **detect_com.py** | 被 start_serial.bat 调用，自动找 ESP32 的 COM 口 | 不用手动跑 |

### Web 前端（web/templates/）

| 文件 | 干什么 | 新手需要改吗 |
|------|--------|-------------|
| **base.html** | 所有页面的**母版**。侧边栏导航、顶栏用户信息、深色主题 CSS 变量（`--bg-dark`/`--accent-blue` 等）、内联 SVG 图标。其他模板 `{% extends "base.html" %}` 继承 | 不用改 |
| **login.html** | 登录页。纯用户名 + 密码，没有注册入口 | 不用改 |
| **dashboard.html** | 看板。7 张 stat-card（**全部可点击跳转**：映射→/mappings、用户→/users、在线→/sessions、采集点→/config-points）+ 3 个占位图表区域（设备接入趋势/状态分布/告警趋势） | 不用改 |
| **mappings.html** | 映射管理。表格列出全部 8 条。新增/编辑弹窗用纯 HTML `<form>`，**admin 能编辑，user 只读（按钮隐藏）**。addModal/editModal 弹窗本身也只在 admin 时输出到 HTML | 不用改 |
| **devices.html** | **实物控制台**。4 路继电器按钮（开/关/全关）+ 当前状态显示 + 传感器卡片（温度/湿度/人体/烟雾），数据实时来自 device_status 缓存 + MQTT 直连下发命令 | 不用改 |
| **sessions.html** | **在线用户追踪**。实时在线卡片（带 5 分钟超时）+ 最近登录历史表格。**同一用户新登录会自动踢旧 session**，不会堆多条 | 不用改 |
| **config_points.html** | **采集点配置**。WiFi/MQTT 基础配置表单 + Modbus 从站/采集点可视化编辑表（addr 0x0000 格式、key、period_ms、type、scale、count）+ 原始 JSON 预览。**普通用户看原始 JSON 时 wifi_pass/mqtt_pass 被脱敏为 `******`** | admin 能编辑，user 只读 |
| **users.html** | 用户管理（仅 admin 可访问）。表格列出所有用户（SHA-256 哈希存密码），可改角色、重置密码、删除 | 不用改 |

### 启动脚本

| 文件 | 干什么 | 双击/手动 |
|------|--------|----------|
| **start_all.bat** | ⭐ **一键启动**：端口冲突检查 → 建库 → ModbusSim → Bridge → Web。3 个 cmd 窗口自动弹出，标题前缀已区分 | **双击它** |
| **start_web.bat** | 只启动 Web 管理后台（8081），不启动模拟器和 Bridge | 只看 Web 界面时用 |

## 运行步骤（从零开始，照着做）

### 准备工作（只需一次）

```powershell
pip install -r requirements.txt
# 需要: paho-mqtt, flask, pyserial, pymodbus
```

### 第 1 步：双击 start_all.bat

会自动弹出 3 个 cmd 窗口：

| 窗口标题 | 跑的命令 | 作用 |
|----------|---------|------|
| ModbusSim-Day9 | `python -u modbus_slave_sim.py 5502 7` | Modbus 模拟器（与 Day8 相同） |
| Bridge-Day9 | `python -u gateway_bridge.py --hot-reload` | Day9 Bridge，带 5 秒热刷新 |
| Web-Day9 | `python -u web\app.py` | Day9 Web 管理后台 |

**Bridge-Day9 正常应显示**（与 Day8 日志不同，多了 SQLite 加载）：
```
[init_db] 数据库就绪: ...\iot_platform.db
[Bridge] 已连接 172.16.4.211:9783
[Bridge] 从 SQLite 加载路由表: 8 个 gateway_key
[Bridge] 订阅网关: relay-cc/relaycc/#
[Bridge] hot-reload 已启用 (每 5 秒检查)
```

**Web-Day9 正常应显示**：
```
 * Running on http://127.0.0.1:8081
```

### 第 2 步：打开 Web 管理界面

浏览器访问 **http://127.0.0.1:8081**

默认账号：
- **admin / admin123** — 全部权限
- **user / user123** — 只读

### 第 3 步：逐一探索 8 个页面

| 页面 | URL | 说明 |
|------|-----|------|
| 看板 | /dashboard | 7 张可点击 stat-card + 3 个图表。card 底部显示"点击查看详情 →"，user 角色的用户/在线 card 会提示"仅管理员可管理" |
| 映射管理 | /mappings | 表格列出全部 8 条路由。admin 能增删改/启用禁用；user 只能看 |
| 实物控制台 | /devices | 4 路继电器开关（**admin 能点** → MQTT 下发直接控板子；user 也能看但后端 403 拦截）。实时显示 device_status 缓存里的温度/湿度/人体/烟雾 |
| 采集点配置 | /config-points | WiFi/MQTT/Modbus 可视化表单。**保存后 config.json 会自动更新**。admin 能编辑；user 看只读视图，原始 JSON 里密码被脱敏为 `******` |
| 在线用户 | /sessions | 实时在线卡片（带 5 分钟超时）+ 最近登录历史 |
| 用户管理 | /users | 仅 admin。增用户/改角色/重置密码/删除。**db 层校验**：空密码/非法用户名/superadmin 角色都会被拒绝 |
| 登录 | /login | admin/admin123 或 user/user123 |
| 退出 | /logout | 正常登出会 end_session 标记 offline |

### 第 4 步：Day9 核心演示——新增一个虚拟设备

假设 JetLinks 上新建了产品 `fan-cc`（风扇）、设备 `fan001`，物模型加属性 `switch`：

| 步骤 | Day8 做法 | Day9 做法 |
|------|-----------|-----------|
| 1 | 在 ESP32 固件加 relay5 控制 | （需要继电器 5 时改固件，此例不改） |
| 2 | **改 gateway_bridge.py** 加 `relay5` 硬编码 | **不用改代码！** |
| 3 | 重启 Bridge | Bridge 自动热刷新（5 秒） |
| 4 | 等 Bridge 生效 | Web 页面点新增就完事了 |

**操作**：登录 admin → 映射管理 → 新增 → 填：
- Gateway Key: `relay1`（随便用一个已有的）
- 虚拟产品 ID: `fan-cc`
- 设备 ID: `fan001`
- 属性名: `switch`
- 描述: 风扇

保存 → 等 5 秒 → Bridge 日志出现 `[Bridge] 路由表已刷新` → JetLinks 上 `fan-cc/fan001` 开始收到数据。

## 权限系统详解

### 前端 + 后端 + db 三层防御

```
用户请求 Web 页面
    │
    ▼
Flask 路由层 (app.py)
    ├── @login_required → 未登录 → redirect /login
    ├── @admin_required → user 角色 → 403 Forbidden
    │
    ▼
db.py 函数层 (源头)
    ├── add_user('bad user!', '123', 'superadmin') → ValueError!
    ├── update_user_role(uid, 'superadmin') → ValueError!
    ├── reset_password(uid, '123') → ValueError!
    └── 任何绕过 Web 直接调 db 的方式都被拦
    │
    ▼
SQLite
    └── device_mappings / users / login_sessions / device_status
```

### 权限矩阵

| 操作 | admin | user | 拦截层 |
|------|-------|------|--------|
| 登录 | ✓ | ✓ | — |
| 看板（可点击跳转） | ✓ | ✓ | — |
| 实物控制台（**看**状态） | ✓ | ✓ | — |
| 实物控制台（**下发**继电器命令） | ✓ | ✗ 后端 403 | @admin_required |
| 采集点配置（**看**） | ✓ | ✓ | — |
| 采集点配置（**保存**） | ✓ | ✗ 后端 403 | @admin_required |
| 原始 JSON 里看密码明文 | ✓ | ✗ 脱敏为 `******` | 后端 safe_json |
| 新增/编辑/删除映射 | ✓ | ✗ 按钮隐藏 + 后端 403 | @admin_required + {% if admin %} |
| 用户管理（增/改角色/重置密码/删） | ✓ | ✗ 侧边栏完全隐藏 | @admin_required |
| 直接 POST 保存采集点 | ✓ | ✗ 后端 403 | @admin_required |

## 登录会话机制

```
用户登录 /login POST
    │
    ▼
db.start_session()  → INSERT login_sessions (status=online)
    │
    ▼
db.kick_user_sessions(keep_session_id=新sid)  → UPDATE 该用户其他 online session → offline
    │
    ▼
Flask session["user"] = {id, username, role, session_id}
    │
    ▼
每次请求 before_request → touch_session() → UPDATE last_seen=NOW
    │
    ▼
list_online_users()
    ├── WHERE status='online' AND last_seen > datetime('now', '-5 minutes')  ← 超时判定
    └── 顺便 UPDATE stale session status='offline'                          ← 清理
    │
    ▼
同一个 user 第二次登录 → kick_user_sessions 踢掉第一次的
    （session 表保留两条历史，但只有最新一条是 online）
```

**为什么这样设计**：保留完整登录轨迹（谁什么时候登进来、用什么 IP），同时在线列表永远是"当前真正活跃的用户"。

## Bridge 热刷新机制

```
Bridge 启动
  ├── init_db()               确保 SQLite 存在
  ├── refresh_routing()       启动时从 DB 加载一次
  │   ├── SELECT * FROM device_mappings WHERE enabled=1
  │   ├── 重建 UP_ROUTING dict
  │   └── 重建 DOWN_ROUTING (反向映射, 自动)
  └── 如果加了 --hot-reload:
        └── 后台线程每 5 秒 refresh_routing()
              ├── 对比新旧路由表
              ├── 有变化 → 打印 "[Bridge] 路由表已刷新, 8 个 key"
              └── 无变化 → 静默跳过 (日志不刷屏)
```

刷新期间 MQTT 收发不中断，用 `_routing_lock` 线程锁保护。

## MQTT 凭据统一配置（Day9 核心改进）

Day8 有 **3 处**硬编码 MQTT 凭据，改一处不同步就出事：

| 硬编码位置 | 值 |
|-----------|-----|
| gateway_bridge.py 顶部 | `MQTT_HOST="172.16.4.211", MQTT_PORT=9783, MQTT_USER="test", MQTT_PASS="123456"` |
| app.py `_get_mqtt()` | 同样的 "test"/"123456"/"172.16.4.211":9783 |
| config.json | 同样的值 |

Day9 统一从 `esp32_firmware/config.json` 读取：

```python
# db.py — 唯一的配置加载入口
def load_gateway_config():
    with open("esp32_firmware/config.json", "r") as f:
        cfg = json.load(f)
    return {
        "mqtt_host": cfg["mqtt_host"],
        "mqtt_port": int(cfg["mqtt_port"]),
        "mqtt_user": cfg["mqtt_user"],
        "mqtt_pass": cfg["mqtt_pass"],
        "product_id": cfg["product_id"],
        "device_id": cfg["device_id"],
        "wifi_ssid": cfg["wifi_ssid"],
        "wifi_pass": cfg["wifi_pass"],
    }
```

然后 gateway_bridge.py 和 app.py 都 `from db import load_gateway_config` 调用。**以后改 MQTT 地址只需要改 config.json 一个地方**。

## 踩坑记录（Day9 实测 + 修复）

### 🔴 坑 9.1：采集点配置保存丢 `period_ms`（采集周期全打回默认 3000ms）

**现象**：admin 在 Web 页面改了 `period_ms=5000` 保存 → config.json 里还是 `period_ms=3000`，永远默认值。

**根因**：表单字段名 `slave_0_period_ms_0` 里有下划线，原代码用 `key.split('_')` 拆分得到 `['slave', '0', 'period', 'ms', '0']`——5 部分。`int('ms')` 报错，被 `continue` 跳过，整条记录没写进去。

**修复**：用**精确正则**匹配而不是 split：
```python
m = re.match(r'^slave_(\d+)_(addr|key|period_ms|type|scale|count|write)_(\d+)$', key)
# period_ms 作为整体被正确识别
```

### 🔴 坑 9.2：普通用户能看到密码明文

**现象**：`/config-points` 页面用 `@login_required` 不是 `@admin_required`——**user 角色也能登录看到页面底部的原始 JSON 卡片**，里面含 `wifi_pass: "yh82922868"`、`mqtt_pass: "123456"` 明文。

**根因**：登录后只看 role 判断按钮显隐，但原始 JSON 卡片直接渲染 `{{ config | tojson }}`，没做脱敏。

**修复**：后端加 `safe_json`——普通用户访问时把 `wifi_pass`/`mqtt_pass`/`mqtt_user` 替换为 `"******"`；前端卡片改用 `{{ safe_json }}` 渲染。admin 看到明文，user 看到脱敏值，还会显示"敏感字段已脱敏"提示。

### 🔴 坑 9.3：db 层没有校验，绕过 Web 直接写脏数据

**现象**：直接在 Python shell 里 `from db import add_user; add_user('bad user!', '123', 'superadmin')`——空密码、非法用户名、3 位短密码、`superadmin` 非法角色**全部能写入**。

**根因**：Day8 写了 `_RE_USER/_RE_PASS/_RE_NAME` 正则在 db.py 顶部，但三个 CRUD 函数（`add_user`/`update_user_role`/`reset_password`）**根本没调**它们。我一开始只在 Flask 路由层加了校验——但 route 能被直接调 db 绕过。

**修复**：在 db.py 的三个函数**入口**加校验（源头防御）：
```python
def add_user(username, password, role="user", display_name=""):
    _validate("username", username, _RE_USER, "用户名")
    _validate("password", password, _RE_PASS, "密码")
    if role not in ("admin", "user"):
        raise ValueError(f"非法角色 '{role}'")
    ...
```

> 教训：**安全校验永远放数据层（db.py），不放展示层（Flask 路由）**。展示层校验是 UX（快速失败给用户友好提示），数据层校验是 security（任何调用方式都拦）。

### 🟡 坑 9.4：关浏览器后用户永远显示在线

**现象**：`list_online_users()` 只认 `status='online'` 字段。用户直接关浏览器不登出 → `status` 永远是 online → 在线用户数虚高。

**根因**：原查询 `SELECT ... WHERE status='online'` 没考虑"这个 online 是 3 天前留下的"。

**修复**：
```sql
SELECT ... FROM login_sessions
WHERE status='online' AND last_seen > datetime('now', '-5 minutes')
```
同时每次查询顺便把 `status='online' AND last_seen <= '-5 minutes'` 的 session 自动标记为 offline。**双重保险**。

### 🟡 坑 9.5：同一用户多次登录堆出 N 条 online session

**现象**：admin 连登 7 次 → 在线用户页面显示 7 个一样的 admin 卡片。

**根因**：login 路由里 `start_session()` 无条件新建一条，没有把之前的踢掉。

**修复**：
```python
sid = start_session(user["id"], user["username"], ip)
kick_user_sessions(user["id"], keep_session_id=sid)
# 同一用户旧 online session 全部变 offline, 只保留刚创建的新这条
# 历史 session 记录保留 (登录轨迹), 不会丢
```

### 🟡 坑 9.6：MQTT 凭据 3 处硬编码，改一处不同步

**现象**：改 config.json 的 MQTT 密码，但 gateway_bridge.py 和 app.py 里还是旧密码 → Bridge/Web 都连不上平台。

**根因**：Day8 直接把 MQTT 常量写死在各文件顶部。

**修复**：db.py 新增 `load_gateway_config()` 函数，从 `esp32_firmware/config.json` 统一读取。gateway_bridge.py 和 app.py 都改为 import 调用。**以后改 MQTT 地址/账号/密码只需要改 config.json 一个地方**。

### 🟢 坑 9.7：config.json.bak 被 git 追踪

**现象**：每次保存 config.json 时程序自动生成 `.bak` 备份文件，git status 总是显示它被修改。`.gitignore` 里虽然有 `*.bak`，但**对已被追踪的文件无效**。

**修复**：
```powershell
git rm --cached simulator/day9/esp32_firmware/config.json.bak
```
从 git 索引里移除，之后 .gitignore 才生效。

### 🟢 坑 9.8：mappings.html 的 addModal/editModal 弹窗 DOM 泄露给 user

**现象**：user 角色登录后看 mappings.html，虽然"新增映射"按钮已隐藏，但查看页面源代码会发现 `addModal` 和 `editModal` 两个弹窗表单的 HTML 仍然存在于 DOM 里（只是看不见）。按钮和后端都拦住了，功能上没漏洞，但不够干净。

**修复**：把两个弹窗 div 包在 `{% if current_user and current_user.role == 'admin' %}` 条件里，user 的 HTML 里完全不输出弹窗代码。

### 🟢 坑 9.9：device_name 校验在 _validate 里会被拦

**现象**：我一开始在 `add_user` 里对 display_name 调了 `_validate("display_name", display_name or "", _RE_NAME, "显示名")`——但 `_validate` 第一条就是 `if value is None or value == "": raise ValueError("不能为空")`。空 display_name 被意外拦了。

**修复**：display_name 可选才校验：
```python
if display_name:
    _validate("display_name", display_name, _RE_NAME, "显示名")
```

## 验收 Checklist

- [ ] `python db.py` 成功建库 + 打印"数据库就绪"
- [ ] 8 条 device_mappings、2 个默认用户（admin/user）在表中
- [ ] `python gateway_bridge.py --hot-reload` 启动后打印"从 SQLite 加载路由表: 8 个 gateway_key"
- [ ] Bridge 日志显示 MQTT 连接 + 订阅 6 个虚拟产品下行
- [ ] 浏览器打开 `http://127.0.0.1:8081` 看到深色主题登录页
- [ ] admin/admin123 登录 → 看到完整 6 个侧边栏菜单
- [ ] user/user123 登录 → 侧边栏只有 3 个（看板/实物/采集点/映射/在线），**用户管理**隐藏
- [ ] user 直接 POST `/users/add` → 后端 403
- [ ] user 直接 POST `/config-points/save` → 后端 403
- [ ] user 看 `/config-points` 原始 JSON → `wifi_pass`/`mqtt_pass` 是 `******`（脱敏）
- [ ] 实物控制台 admin 能点继电器按钮 → MQTT 下发 → Bridge 日志有 `↓ relay1 0 → relaycc/properties/write`
- [ ] 实物控制台显示 device_status 里的温湿度（数字在变，Bridge 在跑）
- [ ] 采集点配置改 `period_ms=5000` 保存 → 读回还是 5000（没被打回 3000）
- [ ] 新增一条映射 → Bridge 日志 5 秒内出现"路由表已刷新"
- [ ] 关闭浏览器 5 分钟 → 再开 → `get_online_count()` 返回 0（或只有当前登录用户）
- [ ] admin 连续登录 3 次 → `list_online_users()` 只有 1 条（最新那条，旧的被踢为 offline）
- [ ] `db.add_user('bad user!', '123', 'superadmin')` → ValueError
- [ ] `db.add_user('', 'goodpass', 'user')` → ValueError
- [ ] `db.reset_password(1, '123')` → ValueError
- [ ] `db.update_user_role(1, 'superadmin')` → ValueError
- [ ] Bridge 和 Web 的 MQTT 连接信息来自 `load_gateway_config()`（不再硬编码）
- [ ] `config.json.bak` 不在 git tracked 列表里

## 常见问题排查

| 现象 | 可能原因 | 解决 |
|------|---------|------|
| 登录页能打开但 admin/admin123 登不进去 | SQLite 被之前的测试脚本改了 admin 密码 | 运行 `python -c "from db import reset_password; reset_password(1, 'admin123')"` |
| 实物控制台点了继电器但板子没反应 | Bridge 没在跑 / MQTT 连不上 / device_id 和 config.json 不一致 | 看 Bridge-Day9 窗口有没有打印 `↓ relayX N → gateway` |
| 实物控制台传感器一直是 -- | Bridge 没收到上报 → device_status 表没数据 | 确认 ModbusSim 和 Bridge 都在跑，板子在上报 |
| 采集点保存后 config.json 没变化 | 浏览器缓存了旧表单 | 强刷页面 Ctrl+F5 再试 |
| Bridge 没打印"路由表已刷新" | hot-reload 参数没加 / Bridge 版本不是 Day9 | 重启 Bridge 加 `--hot-reload` |
| 在线用户页有好多一样的人 | 之前旧版本堆的脏 session | `python db.py` 重建库（或手动清 `DELETE FROM login_sessions`） |
| Bridge/Web 报 MQTT 连接失败 | config.json 里 MQTT 地址/账号错了 | 检查 `172.16.4.211:9783`、`test`/`123456` |

## Day9 学了什么

- **分层安全**：校验放在数据层（db.py）而不是展示层（Flask），展示层校验是 UX，数据层校验是 security
- **配置集中化**：多文件硬编码同一个配置 = 维护灾难。一个 `load_config()` 函数统一读文件
- **会话管理**：新登录踢旧 session + 超时自动判定离线，保持在线列表干净
- **表单解析正则化**：多下划线字段（`slave_0_period_ms_0`）用精确正则匹配不要 split
- **敏感信息脱敏**：前后端配合，后端判断 role 决定是否脱敏，前端不泄露敏感值
- **RBAC 权限矩阵**：三层防御（Flask 装饰器拦截 + 前端隐藏按钮 + db 层源头校验）
- **SQLite 应用模式**：本地小项目用 SQLite 比 MySQL 简单太多——文件即数据库，无需外部服务，首次运行自动建表 + 预填充

---

## 附录：config.json 结构速查

```json
{
  "wifi_ssid": "Office-WiFi",
  "wifi_pass": "yh82922868",
  "mqtt_host": "172.16.4.211",
  "mqtt_port": 9783,
  "mqtt_user": "test",
  "mqtt_pass": "123456",
  "product_id": "relay-cc",
  "device_id": "relaycc",
  "modbus_slaves": [
    {
      "name": "第七组-多寄存器模拟器",
      "host": "192.168.20.59",
      "port": 5502,
      "unit_id": 7,
      "points": [
        {"addr": 0, "key": "temperature", "period_ms": 3000, "count": 1, "type": "uint16", "scale": 0.1},
        {"addr": 1, "key": "humidity",    "period_ms": 5000, "count": 1, "type": "uint16", "scale": 0.1},
        {"addr": 4, "key": "human",       "period_ms": 3000, "count": 1, "type": "uint16", "scale": 1},
        {"addr": 5, "key": "smoke",       "period_ms": 3000, "count": 1, "type": "uint16", "scale": 1}
      ]
    }
  ]
}
```

**Web 页面编辑的就是这张表**。保存后 `config.json` 自动更新，Bridge 需要重启或等待热刷新生效（Bridge 启动时会重新加载）。
