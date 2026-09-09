# Day9 · 设备映射动态管理 + Web 管理平台 + 权限系统

## 当天目标

Day8 时，Bridge 里的 **路由表是硬编码的**（`gateway_bridge.py` 里直接写了 8 条 `UP_ROUTING` 字典）。这带来一个问题：**每新增一个虚拟设备/映射关系，都要改 Python 代码 + 重启 Bridge + 重新刷固件**，非常不灵活。

Day9 的三个核心目标：

1. **映射关系从硬编码 → SQLite 动态管理**：用本地 SQLite 文件数据库存映射，Bridge 启动时自动加载，Web 页面改完后 Bridge 可以热刷新（`--hot-reload` 参数），**零代码改动即可增删虚拟设备**
2. **Web 管理后台（深色主题）**：参考老师演示的 IoT 管理平台界面，做一个 Flask + 纯 HTML/CSS 的管理页面，包含看板统计、映射 CRUD、用户管理
3. **简化版权限系统**：区分 **管理员**（增删改查全部）和 **普通用户**（仅查看），管理员才能改映射和用户

## Day8 → Day9 改了什么

| 对比项 | Day8 | Day9 |
|--------|------|------|
| 路由表存储 | Python 源码硬编码 `UP_ROUTING = {...}` | SQLite 数据库 `db/iot_platform.db` 的 `device_mappings` 表 |
| 新增映射 | 改代码 + 重启 Bridge | 打开 Web 页面 → 点新增 → Bridge 自动生效 |
| Bridge 刷新 | 改完必须重启 | 默认启动时加载一次；加 `--hot-reload` 后每 5 秒自动刷新 |
| 用户系统 | 无 | SQLite `users` 表，区分 admin/user |
| 管理界面 | 无 | Flask Web（深色主题，参考老师截图） |
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
                                         │ 一条 MQTT 消息
                                         ▼
                              ┌──────────────────────┐
                              │  Python Bridge        │
                              │  gateway_bridge.py    │
                              │                      │
                              │  路由表 ← db/iot_platform.db  ← SQLite 动态加载
                              │  (启动加载 / --hot-reload 5秒刷新)
                              └──────────┬───────────┘
                                         │
                                         ▼
                              JetLinks 平台 (6 产品 / 7 虚拟设备)

  ┌──────────────────────────────────────────────────────────┐
  │  Day9 新增: Web 管理后台 (Flask + 深色主题)               │
  │                                                          │
  │  http://127.0.0.1:8081                                   │
  │  ┌──────┐  ┌──────┐  ┌──────────┐  ┌──────────┐          │
  │  │ 看板  │  │映射管理│  │用户管理(仅admin)│  │登录/退出  │          │
  │  └──────┘  └──────┘  └──────────┘  └──────────┘          │
  │                                                          │
  │  后端: db.py (SQLite 数据层, Bridge 和 Web 共用)          │
  │  前端: web/templates/*.html + 深色主题 CSS (纯静态)       │
  └──────────────────────────────────────────────────────────┘
```

## 数据库设计（SQLite）

数据库文件：`day9/db/iot_platform.db`（首次运行自动创建）

### device_mappings 表 — 设备映射关系

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| gateway_key | TEXT UNIQUE | 网关侧采集点 key：relay1, temperature, human... |
| product_id | TEXT | 虚拟产品 ID：lock-cc, sensor-cc... |
| device_id | TEXT | 虚拟设备 ID：lock001, sensorcc... |
| property_name | TEXT | 虚拟属性名：switch, temperature, detected... |
| description | TEXT | 备注说明 |
| enabled | INTEGER | 1=启用（参与路由）、0=禁用 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 最后更新时间 |

### users 表 — 用户账号

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 自增主键 |
| username | TEXT UNIQUE | 登录名 |
| password_hash | TEXT | SHA-256 哈希 |
| role | TEXT | `admin`（管理员，全部权限）/ `user`（普通用户，只读） |
| display_name | TEXT | 显示名 |
| created_at | TIMESTAMP | 创建时间 |

### 预填充数据

首次运行 `db.py` 会自动插入：

**8 条设备映射**（与 Day8 硬编码完全一致，保证向后兼容）：

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

## 代码结构

```
day9/
├── README.md                 ← 本文档
├── requirements.txt          ← Python 依赖 (paho-mqtt, flask)
│
├── db.py                     ← SQLite 数据层 (Bridge 和 Web 共用)
│   ├── init_db()             建表 + 预填充数据
│   ├── load_routing()        加载启用的路由表 → dict (Bridge 用)
│   ├── load_all_mappings()   加载所有映射含禁用 (Web 管理页用)
│   ├── add_mapping() / update_mapping() / delete_mapping()
│   ├── authenticate()        登录验证
│   ├── list_users() / add_user() / update_user_role() / delete_user() / reset_password()
│
├── gateway_bridge.py         ← Day9 Bridge (从 SQLite 加载路由)
│   ├── UP_ROUTING            不再硬编码, 启动时 refresh_routing() 从 DB 加载
│   ├── DOWN_ROUTING          自动反向生成 (不变)
│   ├── refresh_routing()     从 SQLite 重新加载, 支持热刷新
│   ├── --hot-reload          命令行参数: 每 5 秒自动刷新
│   └── MQTT 收发逻辑        与 Day8 完全一致
│
├── modbus_slave_sim.py       ← Modbus 从站模拟器 (从 Day8 复制)
├── set_modbus.py             ← 写传感器值工具 (从 Day8 复制)
├── detect_com.py             ← COM 口检测工具
│
├── start_all.bat             ← 一键启动全部 (模拟器 + Bridge + Web)
├── start_web.bat             ← 只启动 Web 管理后台
│
├── db/
│   └── iot_platform.db       ← SQLite 数据库文件 (首次运行自动创建)
│
├── web/
│   ├── app.py                ← Flask 主应用 (路由 + 鉴权)
│   │   ├── /login            登录页
│   │   ├── /logout           退出
│   │   ├── /dashboard        看板 (统计卡片 + 产品分布 + 网关采集点)
│   │   ├── /mappings         映射管理 (CRUD, admin 可编辑, user 只读)
│   │   ├── /users            用户管理 (仅 admin 可访问)
│   │   └── /api/routing      JSON API (Bridge 或前端轮询用)
│   │
│   └── templates/            ← HTML 模板 (深色主题, 纯静态 CSS)
│       ├── base.html         布局基类 (侧边栏 + 顶栏 + 深色主题变量)
│       ├── login.html        登录页
│       ├── dashboard.html    看板
│       ├── mappings.html     映射管理 (增删改弹窗)
│       └── users.html        用户管理 (改角色/重置密码/删除)
│
└── esp32_firmware/           ← Day8 ESP32 固件副本 (不变)
    ├── boot.py / main.py / ap_config.py / modbus_gw.py / relay_hw.py / app_config.py
    ├── config.json           当前: 192.168.20.59:5502 unit_id=7
    ├── umqtt/simple.py       MQTT 客户端库
    └── _firmware/ESP32_GENERIC_C3-v1.29.0.bin
```

## 5 步运行流程

### 第 0 步：安装依赖（首次）

```bash
pip install -r requirements.txt
```

需要：`paho-mqtt`、`flask`

### 第 1 步：启动全部（一键）

双击 `start_all.bat`，会依次启动：

1. Modbus TCP 从站模拟器（端口 5502，unit_id=7）
2. Python Bridge（带 `--hot-reload`，每 5 秒自动从 SQLite 刷新路由）
3. Web 管理后台（端口 8081）

或者分别启动：
- `start_all.bat` — 全启动
- `start_web.bat` — 只启动 Web

### 第 2 步：打开 Web 管理界面

浏览器访问 **http://127.0.0.1:8081**

默认账号：
- 管理员：`admin / admin123`
- 普通用户：`user / user123`

### 第 3 步：在 Web 页面管理映射

**新增映射**（只有 admin 能操作）：
1. 左侧菜单点「映射管理」
2. 右上角点「＋ 新增映射」
3. 填写 Gateway Key（如 `relay5`）、虚拟产品 ID、设备 ID、属性名
4. 描述可选，默认启用
5. 保存 → Bridge 下一个刷新周期（5 秒）自动生效

**禁用/启用/删除**：每一行右侧的编辑/删除按钮。禁用的映射 Bridge 不会路由。

### 第 4 步：控制 JetLinks 平台

与 Day8 完全一样：在 JetLinks 平台上对门锁/灯/空调/传感器/人体/烟雾 6 个产品 7 个设备发命令。Bridge 自动从 SQLite 读路由表做协议转换。

### 第 5 步：新增虚拟设备的完整链路（演示 Day9 的价值）

假设现在要新增一个"风扇"设备，对应 `relay5` 继电器（假设板子上还有空闲 GPIO）：

| 步骤 | Day8 做法 | Day9 做法 |
|------|-----------|-----------|
| 1. 改固件 | 在 ESP32 固件加 relay5 控制 + config.json 加采集点 | 改 ESP32 固件 + config.json |
| 2. 改 Bridge | `gateway_bridge.py` 加 `relay5` 硬编码 | **不需要改代码！** |
| 3. 重启 Bridge | 必须重启 | Bridge 自动检测 SQLite 变化 |
| 4. 改模拟器 | modbus_slave_sim.py 加寄存器 | 不用改（风扇是 GPIO 直接控制） |
| 5. JetLinks | 新建产品 + 设备 + 物模型 | 新建产品 + 设备 + 物模型 |
| 6. 刷新配置 | 无 | **Web 页面点一下"新增映射"就完事了** |

## 权限系统

Day9 实现了简化版 RBAC（基于角色的访问控制）：

| 操作 | admin | user |
|------|-------|------|
| 登录 | ✓ | ✓ |
| 看板 | ✓ | ✓ |
| 查看映射列表 | ✓ | ✓ |
| 新增/编辑/删除映射 | ✓ | ✗（按钮隐藏） |
| 用户管理（改角色/重置密码/删除） | ✓ | ✗（侧边栏不显示） |
| API /api/routing | ✓ | ✓ |
| 未登录访问任何页面 | → 强制跳登录页 |

权限检查在 `web/app.py` 的两个装饰器：
- `@login_required` — 已登录即可访问
- `@admin_required` — 必须是 admin 角色

## Bridge 热刷新机制

```
Gateway Bridge 启动
  ├── init_db()              确保 SQLite 存在
  ├── refresh_routing()      启动时从 DB 加载一次
  └── 如果加了 --hot-reload:
        └── 后台线程每 5 秒调用 refresh_routing()
              ├── 对比新旧路由表
              ├── 有变化 → 打印 "[Bridge] 路由表已刷新" + 重建 DOWN_ROUTING
              └── 无变化 → 静默跳过
```

刷新期间 MQTT 收发不中断，加了 `_routing_lock` 线程锁保证读写安全。

**生产建议**：开发时用 `--hot-reload` 方便调试；上线时可以不加，启动加载一次就好。

## 冲突注意事项

### 端口占用

| 端口 | 占用者 | 冲突后果 | 解决 |
|------|--------|----------|------|
| 5502 | Modbus 从站模拟器 | 模拟器启动失败 → ESP32 读不到数据 | 关闭旧模拟器或改端口 |
| 8081 | Flask Web 管理后台 | Web 无法访问 | 关闭旧 Web 服务或改 `WEB_PORT` 环境变量 |
| 9783 | EMQX MQTT | Bridge 连不上平台 | 确认 EMQX 正常运行 |

### 启动脚本冲突

`start_all.bat` 会同时起 3 个独立 cmd 窗口，每个窗口标题前缀已区分：
- ModbusSim-Day9
- Bridge-Day9
- Web-Day9

关闭时直接关掉对应的 cmd 窗口即可，互不影响。

### Day8 vs Day9 Bridge 不要同时跑

两个 Bridge 的 `client_id` 不同（Day8=`bridge-python-v1`，Day9=`bridge-day9-v1`），技术上可以同时跑。但**它们订阅同一组 topic**，会导致 MQTT 消息被两份 Bridge 重复消费，JetLinks 会收到重复数据。**建议只留一个 Bridge 进程**。

### 模拟器只跑一个

`modbus_slave_sim.py` 同一台机器只能跑一个（端口 5502 独占）。

## 踩坑记录

### 坑 10.1：Flask session 在多线程 Bridge 中使用

Bridge 启动后 3 秒内，Web 服务如果还没 ready，httptest 脚本可能连接失败。**Bridge 和 Web 是两个独立进程**，各自启动互不阻塞。Web 启动稍慢（Flask 首次导入需要加载模板）。

### 坑 10.2：SQLite 线程安全

SQLite 默认不支持多线程并发写。`db.py` 用了 `get_conn()` 上下文管理器，每个调用开一个新连接 + 自动 commit。Bridge 热刷新是读操作，Web 的写操作走 HTTP 请求（也是短连接），所以没问题。如果未来有高频写，考虑加 WAL 模式：`conn.execute("PRAGMA journal_mode=WAL")`。

### 坑 10.3：Bridge 热刷新期间 MQTT 不中断

`refresh_routing()` 用 `_routing_lock` 保护 `UP_ROUTING`，MQTT 回调在 `handle_gateway_properties_report` / `handle_virtual_write` 里也拿同一把锁。如果刷新期间 MQTT 刚好来消息，会短暂阻塞在锁上（<1ms），不会丢消息。

### 坑 10.4：Web 登录 CSRF 简化

Day9 的 Flask 表单没做 CSRF Token（简化权限系统），内网实验环境够用。如果要对外暴露，需要加 Flask-WTF 或自定义 CSRF 保护。

### 坑 10.5：SQLite 数据库不要手动删

`db/iot_platform.db` 被删后首次运行会自动重建 + 重新预填充 8 条默认路由 + 2 个默认用户。如果改了路由想重置，直接删这个文件再启动即可。**注意：Web 上做的映射修改会丢失！**

### 坑 10.6：普通用户看不到"新增映射"按钮

不是 bug，是权限设计。user 角色侧边栏只有「看板」和「映射管理」，「用户管理」完全隐藏。映射管理页的"新增"按钮也只对 admin 显示。

## 验收 Checklist

- [ ] `python db.py --force` 能成功建库 + 打印 8 条路由 + 2 个用户
- [ ] `python gateway_bridge.py` 能成功从 SQLite 加载路由表（打印 8 个 key）
- [ ] `python gateway_bridge.py --hot-reload` 启动后，在 Web 页面改一条映射 → 5 秒内 Bridge 日志出现「路由表已刷新」
- [ ] Web 登录页 `http://127.0.0.1:8081` 深色主题正常显示
- [ ] admin/admin123 能登录，user/user123 也能登录
- [ ] 普通用户看不到"用户管理"菜单和"新增映射"按钮
- [ ] admin 新增一条映射 → Bridge 刷新后 JetLinks 上新虚拟设备能收到数据
- [ ] admin 禁用一条映射 → 5 秒内 Bridge 不再转发该 gateway_key
- [ ] 关闭 Bridge 再用 Day8 的 gateway_bridge.py 替换，JetLinks 数据正常 → 说明 Day9 路由表与 Day8 硬编码一致
