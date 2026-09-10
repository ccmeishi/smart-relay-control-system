# 人工测试功能详细步骤

> **整合版人工测试清单** — 按步骤执行，覆盖所有可视功能  
> 适用版本：`最终版/` 智能继电器控制系统整合版  
> 预计耗时：完整跑一遍约 **30~45 分钟**

---

## 0. 测试前准备（必做）

### 0.1 启动项目

1. 双击运行 `最终版/start_all.bat`
2. 看到菜单后输入 **`1`**（Start - Simulator Mode，推荐用模拟器，无需硬件）
3. 等待脚本执行完成，看到 **「大屏已打开」「管理后台已打开」** 提示
4. 自动会弹出两个浏览器窗口：
   - 大屏（免登录）：`http://127.0.0.1:8083/`
   - 管理后台登录：`http://127.0.0.1:8083/login`

> 💡 **如未自动弹窗**：手动打开上述两个 URL。

### 0.2 准备两个账号

| 角色 | 用户名 | 密码 | 权限 |
|------|--------|------|------|
| 管理员 | `admin` | `admin123` | 全部功能（含用户/会话/配置） |
| 普通用户 | `user` | `user123` | 设备/映射/场景（无用户管理） |

### 0.3 测试工具准备

- 浏览器：**Chrome / Edge**（推荐 Chrome，便于 DevTools）
- 另一个浏览器窗口（隐身模式）：用于切换账号验证权限
- 后端日志窗口：`最终版/logs/day102.log` 用记事本或 tail 命令保持打开

---

## 1. 大屏测试（免登录，先测）

打开 `http://127.0.0.1:8083/`（管理员/普通用户**不用登录也能看大屏**）。

### 1.1 全局布局

| # | 操作 | 预期 |
|---|------|------|
| 1.1.1 | 观察页面整体布局 | 顶部标题 + 6 个区块（设备概览 / 通道 / 告警 / 趋势 / 规则 / 在线率）整齐分布 |
| 1.1.2 | 调整浏览器窗口尺寸（缩到约 1366×768，再放大） | 整页可**垂直滚动**、内容不溢出、不重叠 |
| 1.1.3 | 按 `F11` 进入全屏 | 大屏无白边、充满屏幕 |

### 1.2 设备概览（DeviceOverview — 左上）

| # | 操作 | 预期 |
|---|------|------|
| 1.2.1 | 观察 4 个传感器卡片 | 显示 `temperature / humidity / human / smoke` 当前值 |
| 1.2.2 | 等待 10~20 秒 | 数值应随 fake_bridge 推送**变化**（温度会上下浮动，湿度同理） |
| 1.2.3 | 观察「最后更新时间」 | 应在 60s 内（超过 60s 卡片会变灰/标离线） |

### 1.3 通道状态（ChannelStatus — 中上）

| # | 操作 | 预期 |
|---|------|------|
| 1.3.1 | 观察继电器列表 | 显示 `relay1` `relay2` 当前开关状态（绿/灰） |
| 1.3.2 | **点击**任意一个继电器开关按钮 | 按钮变为 busy 状态（旋转/禁用），1~2s 后切换状态 |
| 1.3.3 | 同时打开 `logs/bridge.log` 滚动查看 | 应出现 `[api] ↓ MQTT 下发 relay-cc/relaycc/properties/write: {'relayX': 0/1}` |

### 1.4 告警面板（AlarmPanel — 右上）

| # | 操作 | 预期 |
|---|------|------|
| 1.4.1 | 观察告警列表 | 显示活跃告警（红色 badge）+ 已确认（黄色）+ 已清除（灰色） |
| 1.4.2 | 找到任意一条**红色 active** 告警 | 点击「确认」按钮（或勾选）→ 该告警变黄 |
| 1.4.3 | 点击「全部确认」按钮 | 所有 active 变 acknowledged，弹出「已确认 X 条」 |
| 1.4.4 | 点击「全部清除」按钮 | 所有 acknowledged 变 cleared，列表空，弹出「已清除 X 条」 |
| 1.4.5 | 等待 1~2 分钟（让 fake_bridge 重新触发） | 新告警出现（红色 active） |
| 1.4.6 | 看右上「今日告警」数字 | 应同步反映今天的告警总数 |

### 1.5 数据趋势（DataTrend — 中下/左下）

| # | 操作 | 预期 |
|---|------|------|
| 1.5.1 | 观察 4 条数据曲线 | temperature / humidity / smoke / human 各有一条 |
| 1.5.2 | 等待 30s~1min | 曲线右侧**自动滚动**，新增数据点出现 |
| 1.5.3 | 鼠标 hover 在曲线上 | 出现 tooltip 显示「时间 / 值」 |
| 1.5.4 | **切换顶部「温度 / 湿度 / 人感 / 烟雾」tab 按钮** | 曲线立即切换为对应传感器的历史曲线 |

> 💡 说明：当前版本趋势面板**只有传感器 tab 切换**，没有单独的「5min/30min」时间范围选择器。默认展示最近 30 分钟数据。

### 1.6 场景规则（SceneRules — 右下）

| # | 操作 | 预期 |
|---|------|------|
| 1.6.1 | 观察规则列表 | 显示 4 条预置规则（高温断电 / 烟雾告警 / 有人开灯 / 无人关灯） |
| 1.6.2 | 看每条的「触发次数」 | **数字会缓慢增长**（规则 3/4 因 human 频繁变化会增加得快） |
| 1.6.3 | 看「启用」状态 | 都是绿色/启用 |
| 1.6.4 | **点关**任意一条规则的启用开关 | 该规则图标变灰，不再触发；等待 30s 后看「触发次数」应停止增长 |

### 1.7 在线率（OnlineRate）

| # | 操作 | 预期 |
|---|------|------|
| 1.7.1 | 观察大圆环 + 数字 | 显示 `100%` + 「8/8 在线」 |
| 1.7.2 | 等待 fake_bridge 断网窗口（约每 1~2 分钟一次） | 圆环出现橙色 + 「N/8 在线」（N=7 或 8）|
| 1.7.3 | 观察下方设备列表 | 离线设备会标红色/灰色 |

---

## 2. 登录 / 权限测试（先测登录再测管理）

### 2.1 登录页

| # | 操作 | 预期 |
|---|------|------|
| 2.1.1 | 打开 `http://127.0.0.1:8083/login` | 显示登录卡片 |
| 2.1.2 | 故意输入错密码 `admin / 123` | 弹出红色提示「用户名或密码错误」 |
| 2.1.3 | 输入正确 `admin / admin123` | 1s 内跳转到 `/manage/devices` |

### 2.2 权限分级

| # | 操作 | 预期 | 怎么验 |
|---|------|------|--------|
| 2.2.1 | 用 admin 登录 → 看左侧菜单 | 应**全部可见**（设备/映射/场景/**用户/会话/配置**） | 直接看 |
| 2.2.2 | 切换隐身窗口 → 用 user / user123 登录 | 跳转到 `/manage/devices` | 直接看 |
| 2.2.3 | **在 user 窗口的地址栏手动输入并回车**：`http://127.0.0.1:8083/manage/users` | 页面被重定向回 `/manage/devices`（或顶部弹提示「无权限」） | 直接访问 URL |
| 2.2.4 | 在 user 窗口点「管理后台」菜单 | 侧边栏**不显示**用户/会话/配置入口 | 直接看 |

> 🖱️ **2.2.3 具体操作**：不要用鼠标点菜单，而是点浏览器地址栏 → 删掉当前 URL → 输入 `http://127.0.0.1:8083/manage/users` → 按回车。这样才能验证「后端接口权限拦截」是否生效。

### 2.3 登出

| # | 操作 | 预期 |
|---|------|------|
| 2.3.1 | 点击右上角头像 → 「退出登录」 | 跳回 `/login` |
| 2.3.2 | 在隐身窗口重新访问 `/manage/devices` | 自动跳回 `/login`（session 失效） |

---

## 3. 设备控制页（`/manage/devices`）

### 3.1 单条控制

| # | 操作 | 预期 |
|---|------|------|
| 3.1.1 | 进入 `/manage/devices` | 显示继电器表格（relay1/relay2 + 其他虚拟设备） |
| 3.1.2 | 点任意 relay1 的「开启/关闭」按钮 | 按钮短暂变 busy，1s 内状态翻转 |
| 3.1.3 | 同时切到大屏（`/`）观察 ChannelStatus | relay1 状态**实时同步**（不需要刷新） |
| 3.1.4 | 打开 `bridge.log` | 应出现 MQTT 下发日志 |

### 3.2 一键全开/全关

| # | 操作 | 预期 |
|---|------|------|
| 3.2.1 | 点「一键全关」 | 弹出确认框（可选）→ 所有继电器变 OFF |
| 3.2.2 | 等 2s 后点「一键全开」 | 所有继电器变 ON |
| 3.2.3 | 同时看大屏 | ChannelStatus 实时同步 |

### 3.3 频繁切换（压力测试）

| # | 操作 | 预期 |
|---|------|------|
| 3.3.1 | 快速连续点 relay1 按钮 5~10 次 | **不应报错**，最终状态 = 最后一次点击 |
| 3.3.2 | 观察 `bridge.log` | MQTT 下发日志只记最后一次成功的（节流生效） |

---

## 4. 设备映射页（`/manage/mappings`）

### 4.1 列表浏览

| # | 操作 | 预期 |
|---|------|------|
| 4.1.1 | 进入 `/manage/mappings` | 显示所有 key→设备映射（gateway_key / product_id / device_id / property_name / enabled） |
| 4.1.2 | 看 `enabled` 列 | 每行有「启用」开关 |

### 4.2 新增映射

| # | 操作 | 预期 |
|---|------|------|
| 4.2.1 | 点右上「+ 新增映射」 | 弹出表单弹窗 |
| 4.2.2 | 输入：`gateway_key=test_light`、`product_id=light-cc`、`device_id=test001`、`property_name=switch` | 表单可填写 |
| 4.2.3 | 点「保存」 | 弹窗关闭，列表新增一行 |
| 4.2.4 | 在大屏观察新映射是否生效 | 新 key 应出现在数据流里（如不生效可重启 backend） |

### 4.3 编辑映射

| # | 操作 | 预期 |
|---|------|------|
| 4.3.1 | 点任意一行的「编辑」按钮 | 弹窗打开，字段填好 |
| 4.3.2 | 修改 `property_name`，点「保存」 | 弹窗关闭，列表该行更新 |

### 4.4 启用/禁用切换

| # | 操作 | 预期 |
|---|------|------|
| 4.4.1 | 点任意行的「启用」开关 | 切换 enabled 状态，对应 key 应停止/恢复数据采集 |
| 4.4.2 | 观察大屏 DeviceOverview 对应卡片 | 可能变灰/消失 |

### 4.5 删除映射

| # | 操作 | 预期 |
|---|------|------|
| 4.5.1 | 点「删除」按钮（任意一行） | 弹出确认框 |
| 4.5.2 | 确认删除 | 该行消失 |
| 4.5.3 | （可选）尝试删除**被场景规则引用的** key | 应提示「被引用，无法删除」 |

---

## 5. 场景规则页（`/manage/scenes`）

> ⚠️ 此页功能**强依赖**大屏右侧的 `SceneRules` 组件，建议两窗口对照看。

### 5.1 列表与触发次数

| # | 操作 | 预期 |
|---|------|------|
| 5.1.1 | 进入 `/manage/scenes` | 显示规则表格（名称 / 触发条件 / 动作 / 冷却 / 启用 / 触发次数） |
| 5.1.2 | 刷新页面，观察「触发次数」 | 与大屏 SceneRules 显示应一致 |

### 5.2 新增规则

| # | 操作 | 预期 |
|---|------|------|
| 5.2.1 | 点「+ 新增规则」 | 弹出表单（含名称/触发 key/条件/动作/冷却/级别） |
| 5.2.2 | 填一条简单规则：`温度 > 30` → 告警 | 表单可填写 |
| 5.2.3 | 点「保存」 | 列表新增一行 |
| 5.2.4 | 等 30s~1min（让温度变化到 > 30） | 大屏 AlarmPanel 应出现新告警，触发次数 +1 |

### 5.3 编辑 / 启停

| # | 操作 | 预期 |
|---|------|------|
| 5.3.1 | 点任意规则的「编辑」 | 弹窗填好字段 |
| 5.3.2 | 改「冷却时间」为 300s，保存 | 列表更新 |
| 5.3.3 | 点「启用」开关关闭 | 该规则停止触发（看触发次数不再增长） |
| 5.3.4 | 重新启用 | 30s 内恢复触发 |

### 5.4 删除

| # | 操作 | 预期 |
|---|------|------|
| 5.4.1 | 点「删除」任意一行 | 确认后该行消失，大屏 SceneRules 同步消失 |

---

## 6. 用户管理页（`/manage/users`，**仅 admin**）

| # | 操作 | 预期 |
|---|------|------|
| 6.1 | 用 admin 登录 → 进入 `/manage/users` | 显示用户列表（admin / user 两行） |
| 6.2 | 点「新增用户」 | 弹窗（用户名/密码/角色） |
| 6.3 | 新建 `tester / 123456 / user` | 列表新增一行 |
| 6.4 | 用隐身窗口登录 `tester / 123456` | 能登录，能访问 `/manage/devices`，访问 `/manage/users` 被拒 |
| 6.5 | 回 admin 窗口 → 删除 tester | 列表减少一行；tester 再登录应失败 |
| 6.6 | 尝试删除 `admin` 自己 | 应被阻止（提示「不能删除自己」） |

---

## 7. 会话管理页（`/manage/sessions`，**仅 admin**）

| # | 操作 | 预期 |
|---|------|------|
| 7.1 | 进入 `/manage/sessions` | 显示当前活跃会话（每个登录用户的会话条目） |
| 7.2 | 在另一窗口登录 user | 列表新增一个 user 会话 |
| 7.3 | 点「踢出」该会话 | user 窗口自动跳回 `/login`（session 失效） |

---

## 8. 系统配置页（`/manage/config`，**仅 admin**）

| # | 操作 | 预期 |
|---|------|------|
| 8.1 | 进入 `/manage/config` | 显示大屏主题/背景动画/快捷键等开关 |
| 8.2 | 切换任一开关（如「背景动画」） | 切回大屏 `/` 应看到效果变化 |
| 8.3 | 测试快捷键：`F` 全屏、`Esc` 退出、`R` 重连 WS | 应生效 |

---

## 9. 联动测试（核心：端到端）

这一节**模拟老师演示完整链路**，按顺序点：

### 9.1 完整演示流程（5~8 分钟）

| 步骤 | 操作 | 大屏预期 | 后端日志预期 |
|------|------|----------|--------------|
| 1 | 打开大屏 `/` | 8/8 在线，全绿 | 持续记录 GET 200 |
| 2 | 打开管理后台 `/manage/devices` | — | — |
| 3 | 在管理后台点 `relay1` 关闭 | 大屏 ChannelStatus relay1 变 OFF（1s 内） | `[api] ↓ MQTT 下发 ... relay1: 0` |
| 4 | 等 1~2 分钟（让 fake_bridge 触发断网） | 大屏 OnlineRate 圆环变橙色，N/8 在线 | `[fake][断网] ...` |
| 5 | 断网结束后看大屏 | 圆环恢复绿色 | `[fake][断网恢复]` |
| 6 | 等温度 > 35（fake_bridge 会推到 40+） | 大屏 AlarmPanel 新告警 + 场景规则「高温自动断电」触发 → 所有 relay OFF | `[fake][告警] 规则「高温自动断电」触发` + MQTT 下发 |
| 7 | 回到管理后台点「全部清除」 | 大屏告警全清空 | — |
| 8 | 切到普通用户账号验证权限差异 | user 看不到用户/会话/配置 | — |

### 9.2 数据闭环验证

| # | 验证点 | 怎么验 |
|---|--------|--------|
| 9.2.1 | fake_bridge 推数据 → 进 DB → 大屏显示 | 大屏值应每 60s 内变化一次 |
| 9.2.2 | 大屏 toggle → 调 MQTT → 写回 DB | toggle 后看 `device_mappings` 或 `device_status` 对应 value 已翻转 |
| 9.2.3 | 场景规则触发 → MQTT 下发 → 设备响应（模拟） | 看 bridge.log 应有完整链路日志 |
| 9.2.4 | 告警产生 → 入库 → 大屏展示 → 操作 ack → 入库 | 全部状态变化都在 `alarm_records` 表可查 |

---

## 10. 异常 / 边界测试（可选，进阶）

### 10.1 数据库只读

| # | 操作 | 预期 |
|---|------|------|
| 10.1.1 | 故意把 `iot_platform.db` 设为只读（属性 → 只读） | 重启 backend → 启动失败 / 启动成功但写失败 |
| 10.1.2 | 恢复 | 正常 |

### 10.2 端口冲突

| # | 操作 | 预期 |
|---|------|------|
| 10.2.1 | 故意先开另一个程序占 8083 | start_all.bat 启动时提示，**不报错直接退出** |
| 10.2.2 | 关掉占端口的程序再启动 | 正常启动 |

### 10.3 WS 断连重连

| # | 操作 | 预期 |
|---|------|------|
| 10.3.1 | 打开大屏 → 在 DevTools Network 选「Offline」3 秒 → 取消 | 大屏短暂卡顿后**自动恢复**，不需要刷新页面 |
| 10.3.2 | 观察后端日志 | 应出现 `[ws] 大屏断开` 和 `[ws] 大屏已连接` 交替 |

### 10.4 告警风暴

| # | 操作 | 预期 |
|---|------|------|
| 10.4.1 | 让多条规则同时触发（断电/烟雾/有人开灯…） | 大屏告警列表 > 50 条仍能正常滚动 |
| 10.4.2 | 看 `alarm_records` 表 | 持续累积，无丢 |

---

## 11. 验收清单（打印勾选用）

```
□ 1.1 布局正确，1366×768 下整页可滚
□ 1.2 4 个传感器卡片数值随时间变化
□ 1.3 通道 toggle 实时生效 + MQTT 日志可见
□ 1.4 告警 ack/clear 操作正确
□ 1.5 数据曲线自动滚动
□ 1.6 场景规则触发次数正常累加
□ 1.7 在线率断网时正确下降
□ 2.1 登录 / 错密码提示
□ 2.2 admin vs user 菜单差异正确
□ 2.3 登出后无法访问管理页
□ 3.1 单条继电器 toggle 正常
□ 3.2 一键全开/全关正常
□ 3.3 频繁切换不报错
□ 4.1~4.5 映射增删改查 + 启停
□ 5.1~5.4 场景规则增删改 + 触发联动
□ 6.1~6.6 用户管理（仅 admin）
□ 7.1~7.3 会话踢出
□ 8.1~8.3 系统配置开关
□ 9.1 完整演示流程无异常
□ 9.2 端到端数据闭环可追溯
□ 10.x 异常 / 边界处理得当

总用时 ____ 分钟   测试人 ____   日期 ____
```

---

## 12. 常见问题排查

| 现象 | 排查 |
|------|------|
| 大屏白屏 / 加载不出 JS | 看浏览器 Network 是否有 404；清缓存 `Ctrl+Shift+R` |
| 后端启动报「database is locked」 | 残留进程占着 WAL：`Get-Process python \| Stop-Process -Force` 后重启 |
| 后端启动报「Address already in use」 | 8083 被占：`netstat -ano \| grep :8083` 找 PID kill |
| pytest 报 `ModuleNotFoundError: pymodbus` | 装 3.6.x：`pip install "pymodbus==3.6.9"`（**不要装 3.7+**，API 不兼容） |
| 大屏按钮点了没反应 | 看 bridge.log 是否连上 MQTT 172.16.4.211:9783；网络不通会让下发失败 |
| admin 登录后看不到管理菜单 | 检查 `db.py` 中 admin 的 role 字段必须是 `admin`（不是 `user`） |
| 告警「触发次数 = 0」 | 重启 backend 后**所有 trigger_count 从 0 重新累**，等几分钟后会涨 |
| MQTT 下发后设备无响应 | 实物模式需要 ESP32-C3 已连上 broker；模拟器模式只看日志不真控硬件 |

---

## 13. 测试完成后的清理

1. 关闭两个浏览器窗口
2. 回到 `start_all.bat` 窗口按 **`Ctrl+C`**（或在菜单选 `7` 退出）
3. 确认 8083 已释放：`netstat -ano | grep :8083`（应为空）
4. 清理残留 python 进程：`Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force`
5. （可选）清理测试产生的告警：`最终版/logs/day102.log` 保留为测试记录，`iot_platform.db` 可保留或删除
---

## 14. 硬件模式（模式 2）测试步骤

> 适用场景：现场有 **ESP32-C3 实物板 + Modbus 传感器模拟器 + 继电器** 时使用。  
> 与模式 1（模拟器）的唯一区别：**数据来自真实 ESP32 经 MQTT 上报**，控制指令真实下发到硬件继电器。

### 14.1 硬件链路总览

```
ESP32-C3(固件) ──Modbus采集──> 传感器模拟器 192.168.20.59:5502 (unit_id=7)
      │
      └──WiFi──> MQTT Broker 172.16.4.211:9783 (账号 test/123456)
                      │
                      └──> gateway_bridge.py 订阅网关 topic relay-cc/relaycc
                              │
                              ├──> 按 routing table 拆分到 6 个虚拟产品
                              ├──> 写入 SQLite
                              └──> 大屏 WebSocket 实时展示
大屏/后台 ──控制指令──> gateway_bridge.py ──MQTT下行──> ESP32 ──> 继电器吸合/断开
```

### 14.2 硬件准备清单

| # | 物品 | 数量 | 说明 |
|---|------|------|------|
| 1 | ESP32-C3 开发板 | 1 | 已烧录固件（`firmware/` 目录） |
| 2 | 继电器模块 | 1~4 路 | 接 ESP32 GPIO，控制 220V 通断 |
| 3 | 传感器模拟器（Modbus TCP） | 1 | `192.168.20.59:5502`，unit_id=7，跑温度/湿度/人感/烟雾 |
| 4 | 同一局域网 PC | 1 | 能访问 MQTT 172.16.4.211 和传感器 192.168.20.59 |
| 5 | 手机或笔记本 | 1 | 用于 ESP32 首次配网（连热点填表单） |

### 14.3 第一步：烧录固件（如已烧录可跳过）

用 **Thonny**（推荐）或 esptool 把 `最终版/firmware/` 下所有 `.py` + `config.json` 刷进 ESP32-C3：

1. Thonny 打开 → 工具 → 选项 → 解释器选择 **MicroPython (ESP32)**
2. 连接 ESP32（USB 线），Thonny 底部应显示 REPL 提示符 `>>>`
3. 全选 `firmware/` 目录下文件 → 右键 → **上传到设备**（覆盖同名文件）
4. 确认上传后设备根目录有：`boot.py` / `main.py` / `config.json` / `ap_config.py` / `app_config.py` / `modbus_gw.py` / `relay_hw.py` / `umqtt/`

> ⚠️ 固件关键配置已写在 `firmware/config.json`，**不要手动改**，除非现场 WiFi/从机地址变了（改法见 14.4）。

### 14.4 第二步：ESP32 首次配网（AP 模式）

1. ESP32 上电，等待约 3~5 秒
2. 用手机/笔记本搜 WiFi，应看到一个**无密码开放热点**：`RELAY-SETUP-xxxx`（xxxx = 设备 MAC 后 4 位）
3. 连接该热点
4. 浏览器打开 `http://192.168.4.1`（ESP32 网关地址）
5. 在弹出的配置页填：
   - **WiFi 名称**：现场 WiFi（默认 `Office-WiFi`）
   - **WiFi 密码**：现场 WiFi 密码（默认 `yh82922868`）
   - **MQTT 服务器 IP**：`172.16.4.211`（JetLinks/EMQX）
   - **MQTT 端口**：`9783`
   - **产品 ID**：`relay-cc`（网关产品，不要改）
   - **Modbus 从机**：`192.168.20.59:5502`，unit_id=`7`，4 个采集点（temperature/humidity/human/smoke）
6. 点「保存并重启」
7. ESP32 自动重启 → 连接 WiFi → 连接 MQTT

**配网成功的标志**：热点 `RELAY-SETUP-xxxx` 消失，ESP32 板载 LED 常亮或慢闪（不同固件表现不同）。

### 14.5 第三步：启动后端（模式 2）

1. 双击 `start_all.bat`
2. 菜单输入 **`2`**（Start - Hardware Mode）
3. 观察启动日志，应出现：

```
[runner] MQTT broker 可达 → 使用 gateway_bridge.py (真实数据)
[Bridge] 已连接 172.16.4.211:9783
  订阅网关: relay-cc/relaycc/#
```

> ⚠️ **关键判断**：如果日志出现 `回退到 FakeBridge (模拟数据)`，说明后端**没连上 MQTT broker**，说明：
> - 要么 broker 172.16.4.211 挂了 / 网络不通
> - 要么 test/123456 账号不对
> 此时虽然大屏有数据，但那是模拟数据，不是 ESP32 的。

### 14.6 第四步：验证数据链路（上行）

| # | 操作 | 预期 |
|---|------|------|
| 14.6.1 | 打开大屏 `/` | 4 个传感器卡片有值（来自真实 Modbus 采集） |
| 14.6.2 | 看 `logs/bridge.log` | 应出现 `↑ relay-cc/relaycc report: {...}` 上报日志 |
| 14.6.3 | 对比 Modbus 模拟器面板上的寄存器值 | 大屏值 = 寄存器值 × scale（如寄存器 350 → 温度 35.0℃） |
| 14.6.4 | 人为改变 Modbus 模拟器某个寄存器值（如温度） | 大屏温度应 3~5s 内跟随变化 |
| 14.6.5 | 断开传感器模拟器（或拔网线） | 大屏该传感器卡片 60s 后变灰/标离线 |

#### 📝 怎么改寄存器值（三种方式）

**方式 A：用项目自带脚本（推荐）**

```bash
cd E:\shixiproject\traeproject1\最终版\tools

# 一次性设置 4 个值：温度 40℃、湿度 60%、有人、烟雾 80
D:\Python\python.exe set_modbus.py 40 60 1 80

# 只改温度到 40℃
D:\Python\python.exe set_modbus.py --temp 40

# 只改烟雾到 100（触发烟雾告警）
D:\Python\python.exe set_modbus.py --smoke 100

# 只改人体感应（1=有人 / 0=无人）
D:\Python\python.exe set_modbus.py --human 1
```

输出示例：

```
✅ 温度 reg0 = 400  →  40.0°C
✅ 烟雾等级 reg5 = 100
```

**方式 B：本机自起模拟器（共享模拟器不通时）**

```bash
cd E:\shixiproject\traeproject1\最终版
D:\Python\python.exe tools\modbus_slave_sim.py          # 起在 0.0.0.0:5502, unit_id=7
```

然后把 `tools/set_modbus.py` 第 16 行的 `MODBUS_IP = "192.168.20.59"` 改成 `"127.0.0.1"`，再按方式 A 操作。

**方式 C：图形化工具**

用 **Modbus Poll**（Windows，收费试用）/ **QModMaster**（免费开源）/ **ModbusPal**，连接 `192.168.20.59:5502`，Slave ID=7，功能码 `06 Write Single Register`，地址 `0/1/4/5` 分别对应温度/湿度/人体/烟雾。

#### ⚠️ 关键坑：模拟器会自动漂移，手动写入会被覆盖

`modbus_slave_sim.py` 内置 `drift()` 线程，**每 2 秒**自动改寄存器：

| 寄存器 | 自动漂移行为 | 手动写入能维持多久 |
|--------|-------------|-------------------|
| `reg0` 温度 | 每 2 秒 ±0.2℃（范围 -10~60℃） | 好控制，写 40℃ 能维持 **≈50 秒** |
| `reg1` 湿度 | 每 2 秒 ±0.3%（0~100%） | 类似，能维持较久 |
| `reg4` 人体 | **每 10 秒随机切换 0/1** | ⚠️ **最多 10 秒被覆盖** |
| `reg5` 烟雾 | 每 6 秒波动 ±5，偶尔 +20 | 写 100（上限）能维持一会 |

**演示建议**：
- 触发「高温自动断电」→ 写温度最可靠（`--temp 40`，能维持 50 秒以上）
- 触发「烟雾告警联动」→ 写烟雾到 100（`--smoke 100`）
- 触发「有人自动开灯」→ 人体每 10 秒被随机化，**建议写完后立刻在大屏观察**，或连写多次：
  ```bash
  # 连续写 1，抵消随机切换（Windows 下循环 10 次）
  for /L %i in (1,1,10) do (D:\Python\python.exe set_modbus.py --human 1 & timeout /t 1 >nul)
  ```
- 如需**完全稳定**演示，可临时注释掉 `modbus_slave_sim.py` 第 **157 行** 的 `threading.Thread(target=drift, daemon=True).start()`，改完记得还原。

### 14.7 第五步：验证控制链路（下行）

| # | 操作 | 预期 |
|---|------|------|
| 14.7.1 | 在大屏或后台点 `relay1` 开关 | 后端下发 MQTT → ESP32 收到 → **继电器真实吸合/断开**（能听到"咔哒"声） |
| 14.7.2 | 看 `logs/bridge.log` | 应出现 `↓ 虚拟 write ... relay1: 0/1` |
| 14.7.3 | 用万用表量继电器输出端子 | 通断状态与界面一致 |
| 14.7.4 | 点「一键全关」 | 所有继电器同时断开 |

### 14.8 第六步：场景联动实测（硬件真实触发）

| # | 操作 | 预期 |
|---|------|------|
| 14.8.1 | 把 Modbus 模拟器的温度寄存器调到 **> 350**（即 >35℃） | 触发「高温自动断电」规则 → 所有继电器自动断开 |
| 14.8.2 | 把烟雾寄存器调到 **> 50** | 触发「烟雾告警联动」→ 继电器断开 + 大屏告警 |
| 14.8.3 | 把人感寄存器调到 **1** | 触发「有人自动开灯」→ relay2 吸合 |
| 14.8.4 | 把人感调到 **0** | 触发「无人自动关灯」→ relay2 断开（冷却 10s 后） |

### 14.9 硬件模式常见问题

| 现象 | 排查 |
|------|------|
| ESP32 一直发 `RELAY-SETUP-xxxx` 热点 | 配网没保存成功，重新连热点填表单 |
| 后端回退到 FakeBridge | MQTT broker 172.16.4.211:9783 不通，先 `ping 172.16.4.211` |
| 大屏数据全是 0 / 不变 | Modbus 从机 192.168.20.59:5502 没通，检查从机 unit_id 是否为 7 |
| 继电器点了没反应 | 检查 ESP32 的 GPIO 接线 + 固件 `relay_hw.py` 里的引脚定义 |
| 数据有值但温度显示异常大/小 | scale 配错，检查 config.json 里 `scale: 0.1`（寄存器值 ×0.1 = 实际值） |
| MQTT 连上但无数据 | 确认 ESP32 的 `product_id=relay-cc` 和 `device_id=relaycc` 与后端 routing table 一致 |

### 14.10 模式 1 与模式 2 对比速查

| 维度 | 模式 1（模拟器） | 模式 2（硬件） |
|------|------------------|----------------|
| 数据来源 | fake_bridge.py 程序生成 | ESP32 Modbus 真实采集 |
| 控制对象 | 仅写日志，不真控硬件 | 真实继电器吸合/断开 |
| 需要硬件 | 无 | ESP32 + 传感器 + 继电器 |
| 断网模拟 | fake_bridge 定时断网 | 手动拔网线 |
| 演示稳定性 | 高（无硬件风险） | 中（依赖现场网络/硬件） |
| 适用场景 | 日常测试 / 无硬件演示 | 正式答辩 / 验收现场 |

---

## 15. 模式 3：开发模式（Dev Mode — 前端热重载）

> 适用场景：**要改前端代码 / 调样式** 时使用。改完保存，浏览器自动刷新，不用重新 build。

### 15.1 与模式 1 的区别

| 维度 | 模式 1（Simulator） | 模式 3（Dev） |
|------|--------------------|---------------|
| 后端 | 8083（同一套） | 8083（同一套） |
| 前端 | `frontend/dist` 静态产物（8083 直接托管） | **Vite dev server 5173**（源码实时编译） |
| 改前端代码 | 需 `npm run build` 再刷新 | **保存即生效，自动热重载** |
| 访问地址 | http://localhost:8083 | **http://localhost:5173** |
| 需要 node_modules | 不需要（有 dist 即可） | **需要**（`frontend/node_modules`） |

### 15.2 启动步骤

1. 双击 `start_all.bat`
2. 菜单输入 `3`（Start - Dev Mode）
3. 脚本依次做 4 项检查（Python / 依赖 / 端口 8083 / dist），然后：
   - 弹出一个窗口 `IoT-Backend`（后端 8083）
   - 再弹出一个窗口 `IoT-Frontend-Dev`（Vite dev server 5173）
   - 8 秒后自动打开浏览器 → **http://localhost:5173**
4. 观察 `IoT-Frontend-Dev` 窗口，应出现：

```
  VITE v5.x  ready in xxx ms
  ➜  Local:   http://localhost:5173/
  ➜  Network: http://0.0.0.0:5173/
```

### 15.3 验证清单

| # | 操作 | 预期 |
|---|------|------|
| 15.3.1 | 浏览器打开 http://localhost:5173 | 大屏正常显示，与 8083 完全一致 |
| 15.3.2 | 看地址栏 | 是 `5173` 端口，不是 8083 |
| 15.3.3 | 打开 `frontend/src/App.vue`，改一处标题文字并保存 | **浏览器 1~3 秒内自动刷新**，看到新文字（无需手动刷新、无需 rebuild） |
| 15.3.4 | 浏览器 F12 → Network | `/api/*`、`/ws/*` 请求都发给 5173，由 Vite 代理转发到 8083 |
| 15.3.5 | 大屏数据是否在动 | 有（后端 fake_bridge 在推） |

### 15.4 注意事项

- **后端必须同时运行**：Vite 只是前端开发服务器，`/api` 和 `/ws` 靠 `frontend/vite.config.js` 里的代理转发到 8083。若 8083 没起，页面能打开但所有数据请求返回 **HTTP 500 / 连接被拒绝**（已实测）。
- **`node_modules` 缺失会启动失败**：模式 3 只会在 `dist` 不存在时自动 `npm install`。若 `dist` 存在但 `node_modules` 被删过，`npm run dev` 会报 `vite: not found`，手动执行：
  ```bash
  cd E:/shixiproject/traeproject1/最终版/frontend
  npm install
  ```
- **两个端口都要记**：演示看 8083，开发调 5173。用 `stop_all.bat` 可一次性关掉两个。

### 15.5 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 5173 打不开 / `vite: not found` | node_modules 缺失 | `cd frontend && npm install` |
| 页面能开但数据全空、控制台报 500 | 后端 8083 没起 | 用 `stop_all.bat` 全停后重选模式 3（会自动带起后端） |
| 改代码浏览器不刷新 | 改的文件不在 `frontend/src` 内，或 dev server 已崩 | 看 `IoT-Frontend-Dev` 窗口报错；重启模式 3 |
| 5173 端口被占用 | 上次 dev server 没关干净 | 跑 `stop_all.bat` |

---

## 16. 模式 4：仅启动后端（Backend Only）

> 适用场景：**只测 API / 页面已由别人打开 / 远程访问 / 想在不弹浏览器的干净窗口里看后端日志**。  
> 与模式 1 完全一致，唯一区别是**不自动弹浏览器**。

### 16.1 启动步骤

1. 双击 `start_all.bat` → 输入 `4`
2. 同 4 项检查后，弹出 `IoT-Backend` 窗口，**不打开浏览器**
3. 手动访问 http://localhost:8083

### 16.2 验证清单（命令行方式）

```bash
# 1. 端口监听
netstat -ano | findstr ":8083 " | findstr LISTENING

# 2. 大屏页面
curl -s -o NUL -w "HTTP %{http_code}\n" http://localhost:8083/

# 3. 核心 API
curl -s http://localhost:8083/api/overview
curl -s http://localhost:8083/api/alarm-stats
curl -s http://localhost:8083/api/scene-rules
```

预期：端口显示 LISTENING；页面 200；三个 API 均返回 JSON。

### 16.3 模式 1 vs 模式 4

| 维度 | 模式 1 | 模式 4 |
|------|--------|--------|
| DAY102_FORCE_FAKE | 1（模拟器） | 1（模拟器） |
| 自动开浏览器 | ✅ | ❌ |
| 后端行为 | 完全相同 | 完全相同 |

> 两者的后端 100% 一样，**只是「要不要帮你弹浏览器」的区别**。

---

## 17. 模式 5：运行测试（pytest）

> 适用场景：**交付前自检 / 演示前确认没改坏 / 给评委展示「有自动化测试」**。

### 17.1 测试规模

| 文件 | 用例数 | 覆盖内容 | 类型 |
|------|--------|----------|------|
| `tests/test_sensor_simulator.py` | 41 | 寄存器解析、JSON IO、MQTT 命令解析、payload 契约 | mock + tmp_path |
| `tests/test_esp32_modbus_gw.py` | 40 | MBAP 编解码、5 种寄存器类型、SlaveConn 读写+冷却、网关调度、config 一致性 | mock time/socket（**不需真板子**） |
| `tests/test_gateway_bridge.py` | 28 | 路由表自洽、上行拆分、下行 write/invoke、reply 闭环 | mock MQTT 纯逻辑 |
| `tests/test_modbus_slave_sim.py` | 22 | FC 0x03/0x06、unit_id 过滤、drift、并发 | 真实进程 + pymodbus 集成 |
| `tests/test_protocol_consistency.py` | 21 | 三处寄存器布局 / 连接配置一致性 | 纯文件解析 |
| `tests/test_mqtt_integration.py` | 7 | 真实 broker + bridge + 模拟 ESP32/平台 端到端 | amqtt broker + paho-mqtt |
| `tests/e2e/test_e2e_full_chain.py` | 8 | 端到端全链路：overview → device_status → scene_rules → alarm_stats → login → auth/me → relay toggle → clear_all | 真实启动 backend + HTTP |
| **合计** | **166 passed + 1 xfailed** | 约 **90 秒** | |

### 17.2 启动步骤

**方式 A（推荐，与其它模式一致）**：菜单输入 `5`，脚本执行 `python -m pytest tests\ -v --tb=short`。

**方式 B（命令行，可加参数）**：

```bash
cd E:/shixiproject/traeproject1/最终版

# 全部测试
D:/Python/python.exe -m pytest tests\ -v

# 只跑某个文件
D:/Python/python.exe -m pytest tests\test_gateway_bridge.py -v

# 只跑 e2e（端到端全链路）
D:/Python/python.exe -m pytest tests\e2e\ -v

# 只跑单个用例
D:/Python/python.exe -m pytest "tests\e2e\test_e2e_full_chain.py::test_step7_relay_toggle" -v
```

### 17.3 预期结果

```
================== 166 passed, 1 xfailed in 89.79s (0:01:29) ==================
```

- `166 passed` = 158 单测 + 8 e2e
- `1 xfailed` = 1 个「预期失败」用例（**正常现象，不是报错**）
- `0 failed` / `0 errors` 才是健康状态

### 17.4 ⚠️ 关键前置：先停掉旧服务

**运行模式 5 前，务必先跑一次 `stop_all.bat`。**

原因（已实测踩过）：

1. e2e 测试会**自己起一个 backend**（随机端口，`DAY102_FORCE_FAKE=1`），但它写入的是**同一个** `iot_platform.db`
2. 若此时 8083 上还有 backend 在跑，两个进程同时写同一个 SQLite，可能互相加锁
3. 更常见的是：上一轮跑完后残留 **orphan `fake_bridge.py` 子进程**——backend 被强制结束（`proc.terminate()` 是硬杀），`app.py` 里 `finally: runner.stop()` 没执行到，子进程变成孤儿，一直占着数据库的 WAL 锁
4. 结果：新 backend 启动时报 `sqlite3.OperationalError: attempt to write a readonly database`

**症状**：`158 passed` 但出现 **8 个 e2e ERROR**，报错尾部是 `attempt to write a readonly database`。

**解决**：

```bash
# 1. 先停掉所有服务（stop_all.bat 会杀 8083 进程树 + 孤儿 bridge）
stop_all.bat

# 2. 再重跑模式 5 → 恢复正常
================== 166 passed, 1 xfailed ==================
```

> 快速确认是否有孤儿进程：`tasklist | findstr python`，若出现 `fake_bridge.py --hot-reload` 就是孤儿。

### 17.5 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| 8 个 e2e ERROR，`attempt to write a readonly database` | 孤儿 `fake_bridge` 进程占着 SQLite | 先 `stop_all.bat`，再重跑 |
| `ModuleNotFoundError: No module named 'pymodbus'` | 缺测试依赖 | `pip install -r requirements-dev.txt` |
| 22 个 FAILED，全部 modbus 相关 | pymodbus 版本过新（3.15.x 改了 `ModbusTcpClient` 签名） | `pip install pymodbus==3.6.9`（`requirements-dev.txt` 已锁定） |
| `ModuleNotFoundError: No module named 'amqtt'` | 缺 e2e MQTT broker 依赖 | `pip install amqtt` |
| 测试后大屏告警被清空 | e2e 会执行一次 clear-all | 属正常，测试后重启即可 |

---

## 18. 模式 6：清理数据库（Clean Database）

> 适用场景：**演示前想恢复出厂状态**、告警堆积太多、规则/映射被改乱、数据库损坏。

### 18.1 它会做什么

1. **强制结束 8083 上的 backend 进程树**（`taskkill /pid <pid> /f /t`）
2. **清理孤儿 bridge 进程**（按命令行匹配 `fake_bridge` / `gateway_bridge`）
3. **删除 3 个数据库文件**：`iot_platform.db`、`iot_platform.db-wal`、`iot_platform.db-shm`
4. 下次启动时**自动重建**并预填充默认数据

### 18.2 启动步骤

1. 双击 `start_all.bat` → 输入 `6`
2. 出现警告：`This will delete the database. All data - alarms, rules, users - will be lost.`
3. 输入 `Y` 确认（`N` 取消）
4. 看到 `[Clean] Done. A fresh database will be created on next start.`
5. 再选 `1` 重启 → 库重建完成

### 18.3 ⚠️ 会丢什么 / 会恢复什么

| 数据 | 清理后 |
|------|--------|
| 告警记录 `alarm_records` | ❌ 全部清空 |
| 历史数据 `device_status_history` | ❌ 全部清空 |
| 场景规则 `scene_rules` | ♻️ 恢复为 **4 条默认规则** |
| 设备映射 `device_mappings` | ♻️ 恢复为 **8 条默认映射** |
| 用户 `users` | ♻️ 恢复为 **admin/admin123、user/user123** |
| 登录会话 `login_sessions` | ❌ 全部失效（需重新登录） |
| 大屏配置 `dashboard_config` | ♻️ 恢复默认 |

4 条默认规则：高温自动断电（temperature>35）、烟雾告警联动（smoke>50）、有人自动开灯（human==1）、无人自动关灯（human==0）。

### 18.4 验证清理成功

```bash
# 清理后、启动前：文件应不存在
dir iot_platform.db

# 启动后：库重建，表齐全、默认数据就位
D:/Python/python.exe -c "import sqlite3;c=sqlite3.connect('iot_platform.db');print([r[0] for r in c.execute(\"SELECT name FROM sqlite_master WHERE type='table'\")])"
```

### 18.5 替代方案（只想清告警，不想清库）

不想丢规则 / 用户，只想去掉堆积的告警 → 用大屏告警面板的按钮，或直接调接口：

```bash
curl -X POST http://localhost:8083/api/alarms/ack-all     # 全部确认为已处理
curl -X POST http://localhost:8083/api/alarms/clear-all   # 全部清除
```

---

## 19. 六种模式对比速查表

| 模式 | 菜单 | DAY102_FORCE_FAKE | 自动开浏览器 | 前端来源 | 端口 | 典型用途 |
|------|------|-------------------|--------------|----------|------|----------|
| **模拟器** | `1` | `1` | ✅ 8083 | dist 静态产物 | 8083 | 日常测试 / 无硬件演示（**推荐**） |
| **硬件** | `2` | `0` | ✅ 8083 | dist 静态产物 | 8083 + ESP32 | 正式答辩 / 真实继电器验收 |
| **开发** | `3` | `1` | ✅ 5173 | Vite dev（热重载） | 8083 + **5173** | 改前端代码 / 调样式 |
| **仅后端** | `4` | `1` | ❌ | dist 静态产物 | 8083 | 只测 API / 远程访问 |
| **跑测试** | `5` | — | — | — | 随机端口 | 交付自检 / 展示自动化测试 |
| **清库** | `6` | — | — | — | — | 恢复出厂状态 |
| 退出 | `7` | — | — | — | — | — |

**一句话选型**：

- 普通演示 → `1`
- 连真板子 → `2`
- 改前端 → `3`
- 只想要后端 → `4`
- 交付前自检 → `5`（**先跑 `stop_all.bat`**）
- 演示前重置 → `6`

---

## 20. 停止服务（stop_all.bat）

所有模式启动的服务，统一用 `stop_all.bat` 关闭（比直接关窗口可靠）。

### 20.1 清理逻辑

| 步骤 | 动作 |
|------|------|
| 1/3 | 按端口 8083 找到 backend PID，`taskkill /pid <pid> /f /t` **杀整棵进程树** |
| 2/3 | 按端口 5173 找到 Vite dev server PID，同样杀进程树 |
| 3/3 | 按命令行匹配，清理孤儿 `fake_bridge` / `gateway_bridge` 进程 |
| 兜底 | 按窗口标题 `IoT-Backend*` / `IoT-Frontend-Dev*` 再杀一遍 |
| 验证 | 等 3 秒后复查 8083 / 5173 是否释放，输出 `All services stopped cleanly.` |

### 20.2 使用建议

- **每次重新测试前**都跑一次，可规避「端口被占用」「数据库只读」两个高频坑
- 关不掉时手工兜底：

  ```bash
  netstat -ano | findstr ":8083 " | findstr LISTENING
  taskkill /pid <上面查到的PID> /f /t
  ```

- 只想确认有没有残留：

  ```bash
  tasklist | findstr python
  ```

  若出现 `fake_bridge.py` 或 `gateway_bridge.py`，就是孤儿，跑 `stop_all.bat` 清掉。

---

> **附录：六种模式全流程速记**
>
> ```
> 演示        → start_all.bat → 1 → 浏览器 8083 → 走第 1~13 节
> 连硬件      → start_all.bat → 2 → 看日志确认 gateway_bridge → 走第 14 节
> 改前端      → start_all.bat → 3 → 浏览器 5173 → 改代码自动刷新
> 交付自检    → stop_all.bat → start_all.bat → 5 → 166 passed
> 演示前重置  → start_all.bat → 6 → Y → 再选 1
> 全部结束    → stop_all.bat
> ```
