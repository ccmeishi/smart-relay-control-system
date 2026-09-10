# Day10 · 场景联动 + 告警机制（平台从「被动看」变「主动管」）

## 当天目标（先看懂这一天在干什么）

Day8 / Day9 做好后，平台已经能看到温湿度、人体、烟雾、4 路继电器的实时数据，也能在网页上手动开关电器。但它有个短板：**只会「被动展示」，不会「主动处理」**。

想象几个真实场景：

- 屋里**温度冲到 36°C**，有火灾隐患——人不可能一直盯着屏幕，希望系统**自动把所有电器断电**；
- **烟雾超标**——希望系统**立刻弹一条严重告警**，同时断电；
- **有人走进房间**（人体感应=1）——希望**自动把灯打开**；人走了（=0）**自动关灯**省电。

Day10 就给平台加上这套「**IF 条件满足 → THEN 自动做事**」的能力，叫**场景联动（规则引擎）**；规则一触发，同时产生一条**告警**，管理员在网页上「确认 → 清除」，形成闭环。

- **场景联动**：采集点满足条件时，自动控制设备（高温→全关、有人→开灯）
- **告警机制**：每条规则触发都留一条记录，支持 `未确认 → 已确认 → 已清除` 三态流转
- **Web 管理**：浏览器里零代码增删改规则、查看/确认/清除告警
- **看板统计**：首页新增「场景规则数」「未确认告警数」卡片和告警分布图

> ⚠️ **运行环境提醒**：Day10 的数据来自**真实 ESP32 板子 → EMQX(MQTT) → Bridge** 这条链路，需要实验室环境（板子 + MQTT 服务器 `172.16.4.211` + Modbus 模拟器）。
> **如果手头没有板子 / 连不上实验室 MQTT，只想在自己电脑上看效果，请直接用 [day10_2](../day10_2/README.md)**——它内置了 `fake_bridge.py` 模拟数据源，双击就能跑出完整的场景联动 + 告警 + 大屏，不需要任何硬件。

## 最终架构

```
┌──────────────┐  Modbus TCP   ┌──────────────────────┐
│ Modbus 模拟器 │ ←读 温/湿/人/烟→│   ESP32-C3 网关       │
│ 192.168.20.59 │              │   (relay-cc/relaycc)  │
│    :5502      │              │  4路继电器 + 采集      │
└──────────────┘              └──────────┬───────────┘
                                         │ 一条 MQTT 上报(8个key混在一起)
                                         ▼
                          ┌──────────────────────────────┐
                          │  Python Bridge  gateway_bridge.py │
                          │  ① 按路由表拆给 7 个虚拟设备(Day9)  │
                          │  ② 【Day10新增】评估场景规则         │
                          │  ③ 命中→自动发 MQTT 控制继电器       │
                          │  ④ 命中→写一条告警 + MQTT 告警通知   │
                          └──────────┬───────────────────┘
                                     │ 都落库到 SQLite
                                     ▼
                          ┌──────────────────────────────┐
                          │  SQLite  iot_platform.db (6张表)│
                          │   …Day9 的 4 张表…               │
                          │ + scene_rules   场景规则(新增)   │
                          │ + alarm_records 告警记录(新增)   │
                          └──────────┬───────────────────┘
                                     │ 读取
                                     ▼
                          ┌──────────────────────────────┐
                          │  Flask Web 管理后台  :8081      │
                          │   /scenes 规则管理  /alarms 告警 │
                          │   /dashboard 看板(告警角标)      │
                          └──────────────────────────────┘
```

## 代码结构（day10 文件夹里有什么）

```
day10/
├── start_all.bat            ⭐ 一键启动: 自动开 3 个窗口(模拟器+Bridge+网页)
├── requirements.txt         Python 依赖清单
│
├── db.py                    ⭐ 数据层: 6 张表 + 场景规则评估引擎
├── gateway_bridge.py        ⭐ Bridge: 拆数据(Day9) + 场景联动/告警(Day10新增)
├── modbus_slave_sim.py      Modbus 从站模拟器(假装是温/湿/人/烟传感器)
├── set_modbus.py            手动改模拟器传感器值(触发规则用)
├── detect_com.py            自动探测 ESP32 串口号
│
├── web/                     ← Flask 网站(电脑上跑)
│   ├── app.py               ⭐ 网站主程序(Day10新增 /scenes /alarms 路由)
│   └── templates/           网页模板(深色主题)
│       ├── base.html            所有页面的公共框架(顶栏+告警红点)
│       ├── login.html           登录页
│       ├── dashboard.html       ⭐ 首页看板(新增告警/规则统计卡)
│       ├── scenes.html          ⭐【新增】场景规则管理(增删改/启停)
│       ├── alarms.html          ⭐【新增】告警记录(确认/清除/筛选)
│       ├── devices.html         实物控制台(网页点继电器)
│       ├── mappings.html        设备映射管理(Day9)
│       ├── config_points.html   采集点配置(Day9)
│       ├── users.html           用户管理(Day9)
│       └── sessions.html        在线用户(Day9)
│
├── esp32_firmware/          ← 刷进 ESP32 的固件(和 Day9 一致, 无需重刷)
│   ├── config.json             WiFi/MQTT/Modbus 配置
│   ├── boot.py / main.py       启动入口 / 主循环
│   ├── ap_config.py / app_config.py   配网热点 / 配置读写
│   ├── modbus_gw.py            Modbus 采集
│   ├── relay_hw.py             4 路继电器 + 按键
│   └── umqtt/simple.py         MQTT 库
│
└── db/                      ← 数据库(首次运行自动生成, 不用手建)
    └── iot_platform.db
```

## 每个代码文件是干什么的（新手逐个看）

### 电脑端核心（在电脑上用 Python 跑）

| 文件 | 干什么 | 新手要改吗 |
|------|--------|-----------|
| **start_all.bat** | ⭐ **双击它就行**。自动初始化数据库，然后弹出 3 个黑窗口分别跑模拟器、Bridge、网站 | 不用改 |
| **db.py** | ⭐ 数据库「大管家」。建 6 张表、预填 8 条路由 + 2 个账号 + 4 条场景规则；**最关键的是 `evaluate_scene_rules()`**：每来一个传感器值，它判断命中哪些规则、过没过冷却期，返回要执行的动作 | 不用改 |
| **gateway_bridge.py** | ⭐ Bridge。Day9 负责拆数据；**Day10 在它收到上报时多调一次规则评估，命中就自动发 MQTT 控继电器 + 写告警**。带 5 秒热刷新（网页改了规则不用重启） | 不用改 |
| **modbus_slave_sim.py** | 假传感器，监听 5502 端口给板子读温/湿/人/烟，数值会自己飘动 | 不用改 |
| **set_modbus.py** | 一次性小工具：手动把传感器值改成你想要的（比如温度 36），用来**制造一次规则触发** | 触发时用 |
| **web/app.py** | 网站后台。Day10 新增了 `/scenes`（规则增删改）和 `/alarms`（告警确认/清除）等十几个路由，端口 **8081** | 不用改 |

### 网页模板（web/templates/，不用碰，知道每页对应什么即可）

| 页面 | 网址 | 作用 |
|------|------|------|
| dashboard.html | `/dashboard` | 首页看板：8 张统计卡，含「场景规则数」「未确认告警数」 |
| scenes.html | `/scenes` | **场景规则**列表，可新增/编辑/删除/启用停用（仅管理员） |
| alarms.html | `/alarms` | **告警记录**列表，可按状态/级别筛选，确认/清除/批量操作 |
| devices.html | `/devices` | 实物控制台，网页点 4 路继电器 |
| 其余 mappings/config_points/users/sessions | 同名路径 | Day9 的映射/采集点/用户/在线会话管理 |

### 板子端（esp32_firmware/）

与 Day9 完全相同，**Day10 不用重新刷固件**。各文件作用见 [day8/README.md 板子端章节](../day8/README.md#板子端esp32_firmware刷进-esp32)。

## 数据库新增的两张表（Day10 在 Day9 的 4 张表上加的）

> Day9 已有：`device_mappings`（设备映射）、`users`（用户）、`login_sessions`（登录会话）、`device_status`（最新状态缓存）。

### scene_rules（场景规则）

一条规则就是一句中文：**「当 trigger_key 满足 运算符+阈值 时，做 action_type 动作，并产生一条 alarm_level 告警」**。

| 字段 | 含义 | 例子 |
|------|------|------|
| name | 规则名字 | 高温自动断电 |
| trigger_key | 盯哪个采集点 | temperature |
| trigger_operator | 比较符（`> < >= <= == !=`） | `>` |
| trigger_value | 阈值（存文本，比的时候转数字） | 35 |
| action_type | 动作类型 | all_relay_off |
| action_target / action_value | set_relay 时的目标路/值 | relay2 / 1 |
| alarm_level | 告警级别 info / warning / critical | critical |
| enabled | 1 启用 0 停用 | 1 |
| cooldown_sec | **冷却秒数**：触发后这么多秒内不再重复触发 | 60 |
| trigger_count / last_triggered | 累计触发次数 / 上次触发时间（存在数据库，重启不清零） | 12 / … |

**动作类型只有 4 种**：`set_relay`（控单路）、`all_relay_off`（全关）、`all_relay_on`（全开）、`send_alarm`（只告警不动设备）。

### alarm_records（告警记录）

| 字段 | 含义 |
|------|------|
| rule_id / rule_name | 来自哪条规则（规则被删也保留名字快照）；手动告警 rule_id 为空 |
| source_key / source_value | 触发时的采集点和当时的值 |
| level | info / warning / critical |
| message | 告警描述（如「温度 36.0 超过阈值 35，已全关继电器」） |
| status | active / acknowledged / cleared |
| triggered_at / acknowledged_at / acknowledged_by | 触发时间 / 确认时间 / 确认人 |

### 系统预填的 4 条示例规则（首次运行自动建好）

| # | 名称 | 条件 | 自动动作 | 级别 | 冷却 |
|---|------|------|---------|------|------|
| 1 | 高温自动断电 | temperature > 35 | 全关继电器 | critical 严重 | 60s |
| 2 | 烟雾告警联动 | smoke > 50 | 全关继电器 | critical 严重 | 30s |
| 3 | 有人自动开灯 | human == 1 | 打开继电器2(灯1) | info 提示 | 10s |
| 4 | 无人自动关灯 | human == 0 | 关闭继电器2(灯1) | info 提示 | 10s |

## 运行步骤（从零开始，照着做）

### 准备工作（只需一次）

1. 装 Python 依赖：
   ```powershell
   cd simulator\day10
   pip install -r requirements.txt
   ```
   （主要是 flask、paho-mqtt、pyserial、pymodbus）
2. 实验室环境就绪：ESP32 已刷固件并配好网（能连 WiFi 和 MQTT `172.16.4.211:9783`），板子 Modbus 指向模拟器。
3. 知道网站账号：管理员 `admin / admin123`，普通用户 `user / user123`。

> 没有板子 / 不在实验室？请改用 **[day10_2](../day10_2/README.md)**，纯电脑模拟。

### 步骤 1：双击一键启动

双击 **`start_all.bat`**。它会先初始化数据库，然后自动弹出 **3 个黑色 cmd 窗口**：

| 窗口标题 | 跑的程序 | 作用 | 正常现象 |
|----------|---------|------|---------|
| **ModbusSim-Day10** | `modbus_slave_sim.py 5502 7` | 假传感器，监听 5502 | 打印「从站模拟器已启动 …:5502 unit_id=7」 |
| **Bridge-Day10** | `gateway_bridge.py --hot-reload` | 拆数据 + 场景评估 | 打印「已连接 MQTT」「路由表已刷新 (8 个 key)」 |
| **Web-Day10** | `web/app.py` | 管理网站 | 打印「Running on http://127.0.0.1:8081」 |

> 启动前脚本会自动检测 5502 / 8081 端口是否被占用，被占会提示你先关旧窗口。

### 步骤 2：登录网站、认识两个新页面

浏览器打开 **http://127.0.0.1:8081**，用 `admin / admin123` 登录。

- 点顶部菜单 **场景联动（/scenes）**：能看到预填的 4 条规则，每条显示条件、动作、级别、是否启用、触发次数。
- 点 **告警信息（/alarms）**：初始可能是空的（还没触发过）或列出历史告警。
- 回 **首页看板（/dashboard）**：能看到「场景规则数」「未确认告警数」卡片；有未确认告警时，顶栏铃铛图标会有红色脉冲点。

### 步骤 3：先试「手动测试告警」（最快，不依赖硬件数据）

在 `/alarms` 页面点 **「测试告警」** 按钮 → 选级别（info/warning/critical）→ 写一句话 → 提交。

列表立刻多出一条 `active（未确认）` 告警。然后试三个操作：
- 点 **确认** → 状态变 `已确认`；
- 点 **清除** → 状态变 `已清除`；
- 多造几条后点 **全部确认 / 全部清除** 批量处理。

### 步骤 4：制造一次真实的「场景联动」（高温自动断电）

在**能连到模拟器的电脑**上，新开一个 cmd：

```powershell
cd simulator\day10

# 位置参数直接填「真实单位」: 温度°C 湿度%RH 人体(0/1) 烟雾(0~100)
python set_modbus.py 36 60 1 50
```

这行把温度基准设成 **36°C**（>35），板子下次采集读到后上报 → Bridge 命中规则 1 → **自动把 4 路继电器全部断开**，同时写一条 critical 告警。

观察三处：
1. **板子**：继电器咔哒全断开；
2. **Bridge-Day10 窗口**：打印 `[场景] 规则「高温自动断电」命中 … → 全关继电器 [严重]`；
3. **网站 /alarms**：出现一条红色 critical 告警「高温自动断电」，点确认、清除走完三态。

> 想单独触发别的规则：
> ```powershell
> python set_modbus.py --human 1    # 有人 → 自动开灯(继电器2)
> python set_modbus.py --human 0    # 无人 → 自动关灯
> python set_modbus.py --smoke 60   # 烟雾60 > 50 → 烟雾告警联动
> ```

> 想让温度恢复正常：`python set_modbus.py 26 60 1 10`。

### 步骤 5：在网页上自己加一条规则（可选，体验零代码配置）

`/scenes` → 新增规则，例如：
- 名称：湿度超限提醒；盯 `humidity`，`>`，阈值 `70`；动作用 `send_alarm`（只告警不控设备）；级别 `warning`；冷却 30 秒。
- 保存后规则立即生效（Bridge 每 5 秒热刷新，**不用重启**）。把湿度写到 75 即可看到它触发。

## 一条规则是怎么跑起来的（执行流程）

```
ESP32 上报 temperature=36
        │
        ▼
Bridge handle_gateway_properties_report()
        ├─ update_device_status('temperature', 36)     先存最新值
        ├─ evaluate_scene_rules('temperature', 36)      ↓ 规则引擎判断
        │     1. 查 enabled=1 且 trigger_key='temperature' 的规则
        │     2. 冷却期到了吗？(now - last_triggered >= cooldown_sec)
        │     3. 36 > 35 ？→ 命中规则1，返回动作 + trigger_count+1
        ▼
execute_scene_actions([动作])
        ├─ all_relay_off → 发 MQTT {relay1:0..relay4:0} 给板子
        └─ create_alarm(...) → alarm_records 加一条 active 记录
                              → MQTT 发 /system/alarm/notify
        ▼
网页每 30 秒轮询 /api/alarm-stats → 顶栏红点 + 看板未确认数 +1
管理员在 /alarms 点确认(→acknowledged)、清除(→cleared)
```

### 防冲突设计（多条规则同时命中时）

如果「高温断电（严重）」和「有人开灯（提示）」同一刻命中，谁先执行？Bridge 的策略：
1. **按告警级别排序**：critical > warning > info，严重的先做；
2. 严重规则执行全关/全开后，会把 4 路继电器**锁定一个冷却周期**；
3. 这期间低优先级规则想再开某路灯，会因为「目标被高优先级规则锁定」而**跳过**，避免刚被高温断电又被人感规则把灯打开。

## 告警三态流转

```
┌─────────┐  管理员确认   ┌──────────────┐  管理员清除   ┌──────────┐
│ active  │ ───────────→ │ acknowledged │ ───────────→ │ cleared  │
│ 未确认   │              │   已确认      │              │  已清除   │
└─────────┘              └──────────────┘              └──────────┘
     │                            ▲                          ▲
     └──────────── 管理员可直接清除 └──────────────────────────┘
```

- **active 未确认**：刚产生，需要管理员关注；
- **acknowledged 已确认**：管理员知道了，稍后处理；
- **cleared 已清除**：处理完毕，记录归档保留（不删除，方便回溯）。

## 权限矩阵（管理员 vs 普通用户）

| 功能 | admin | user |
|------|:-----:|:----:|
| 查看规则 / 告警 / 看板 | ✅ | ✅ |
| 新增、编辑、删除、启停规则 | ✅ | ❌ |
| 确认 / 清除 / 批量确认 / 批量清除告警 | ✅ | ❌ |
| 手动产生测试告警 | ✅ | ❌ |
| 网页控制继电器、全开全关 | ✅ | ❌ |

普通用户只能看；所有写操作只有 admin 能做。规则、用户等输入在 `db.py` 源头和 Flask 路由两层都做了正则白名单校验。

## Day9 vs Day10 对比

| 对比项 | Day9 | Day10 |
|--------|------|-------|
| 平台姿态 | 被动展示数据 | **主动联动 + 主动告警** |
| 设备控制 | 只能手动点 | 手动 + **规则自动触发** |
| 异常处理 | 无 | 规则触发告警 + 自动动作 |
| SQLite 表 | 4 张 | **6 张**（新增 scene_rules、alarm_records） |
| Web 页面 | 8 个 | **新增 /scenes、/alarms** |
| 规则配置 | 无 | 网页零代码 CRUD + Bridge 5 秒热刷新 |

## 故障排查（新手最容易遇到的坑）

| 现象 | 原因 | 解决 |
|------|------|------|
| 网页能打开但**没有任何数据/告警** | 没有真实 ESP32 上报，或板子没连 MQTT | Day10 依赖真实链路；纯电脑演示请用 [day10_2](../day10_2/README.md) 的 fake_bridge |
| 设了温度规则却不触发 | 见下面「set_modbus 单位坑」 | 确认填的是真实单位 36，不是 360 |
| `set_modbus.py` 报连接失败/超时 | 它默认连 `192.168.20.59:5502`（写死在文件顶部 MODBUS_IP） | 在能访问模拟器的电脑上跑；本机自测就把 `set_modbus.py` 顶部 `MODBUS_IP` 改成 `127.0.0.1` |
| 规则第一次不触发、要等一下 | 传感器单次抖动防误报 + 冷却期；规则刚触发过在冷却内 | 属正常；调大/调小 `cooldown_sec`，或等冷却结束 |
| 告警一直重复刷 | 冷却时间太短或条件一直成立 | 把规则 `cooldown_sec` 调大；让传感器值回到阈值内 |
| 网页顶栏告警红点不消失 | 还有 active 未确认告警 | 去 `/alarms` 把告警确认并清除（或全部清除） |
| 网页改了规则不生效 | Bridge 没用 `--hot-reload` 启动 | 用 start_all.bat 启动（已带热刷新），或重启 Bridge 窗口 |
| /scenes、/alarms 里没有操作按钮 | 当前登录的是普通用户 user | 退出，用 `admin/admin123` 登录 |
| Bridge 窗口没「已连接」 | MQTT 服务器不通 | 确认能访问 `172.16.4.211:9783`、账号 test/123456 |
| 8081 网页打不开 | 端口被旧进程占用 | 关掉旧 Web-Day10 窗口，或 `netstat -ano | findstr :8081` 找到进程结束 |
| 双击 start_all.bat 乱码/闪退 | bat 编码或换行被改坏 | 本项目 bat 用纯英文 + CRLF；被改坏就从仓库重新拉取 |

### ⚠️ 重点坑：set_modbus.py 的单位是「真实单位」，不是寄存器原始值

`set_modbus.py` 命令行填的是**摄氏度 / 百分比这种真实单位**，程序内部会自动 ×10 写成 Modbus 寄存器原始值（板子再 ÷10 还原）。

```powershell
python set_modbus.py 36 60 1 50
#                       ↑ 这就是 36.0°C（程序内部自动写成寄存器 360，板子读回 36.0）
```

所以：
- ✅ 想造 36°C 高温：`python set_modbus.py 36 ...`
- ❌ 不要填 `360`——那会被当成 **360°C**，反而对不上（旧版文档此处写反了，已纠正）。

## 验收清单

- [ ] `pip install -r requirements.txt` 成功
- [ ] 双击 start_all.bat，3 个窗口（ModbusSim / Bridge / Web）都正常、端口无冲突
- [ ] 浏览器打开 http://127.0.0.1:8081，admin/admin123 能登录
- [ ] /scenes 能看到预填的 4 条规则；/alarms 页面能打开
- [ ] 「测试告警」能产生 active 告警，确认→已确认、清除→已清除，批量按钮有效
- [ ] `python set_modbus.py 36 60 1 50` 后，Bridge 窗口打印「高温自动断电」命中
- [ ] 板子 4 路继电器自动全断开（无板子时至少 Bridge 打印动作 + 网站出现 critical 告警）
- [ ] /alarms 出现 critical 告警，三态流转正常，顶栏红点随确认/清除消失
- [ ] 普通用户 user 登录看不到任何写操作按钮
- [ ] 网页新增/停用规则后，不重启 Bridge，约 5 秒内自动生效

## Day10 学了什么

- **规则引擎 / 场景联动思想**：把「IF 条件 THEN 动作」抽象成数据表配置，不写死在代码里（智能家居、工业告警的通用模式）；
- **告警三态闭环**：产生 → 确认 → 清除，为什么要留状态和确认人（可追溯）；
- **防抖三保险**：传感器稳定判定 + 冷却时间 + 告警级别优先级/继电器锁，避免抖动乱触发和规则打架；
- **热刷新**：Bridge 定时重读 SQLite 配置，改规则不用重启服务；
- **规则评估放在数据入口（Bridge）而不是网页**：保证即使没人看网页，联动照样自动执行。

---

## 附录：手动分步启动（start_all.bat 出问题时用）

```powershell
cd simulator\day10

python db.py                                   # 1. 初始化数据库（建表+预填）
python modbus_slave_sim.py 5502 7              # 2. 新窗口：Modbus 模拟器
python gateway_bridge.py --hot-reload          # 3. 新窗口：Bridge(带场景评估)
python web\app.py                              # 4. 新窗口：网站 :8081
```

刷固件 / 配网 / 串口监控等板子相关操作与 Day8 完全相同，见 [day8/README.md 附录](../day8/README.md#附录刷固件与配网板子是旧固件没配网时才需要)。
