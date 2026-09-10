# 06 - 常见问题

## 1. 双击 start_all.bat 闪退

Windows 批处理对格式敏感，常见原因：
- **行尾非 CRLF**：若用 LF（Git/编辑器默认），`setlocal` 等命令解析失败。确保 `.bat` 以 CRLF 保存。
- **含非 ASCII 字符**：bat 主体只允许 ASCII 英文；要输出中文必须先 `chcp 65001`（脚本已加）。
- **if 块内字面括号**：`if (...)` 块里出现 `()` 会让解析器提前结束块。脚本已规避，自行修改时勿加。
- **缺 `pause`**：任何退出路径都应 `pause`，否则窗口直接关闭看不到错误。

排查：在 cmd 中手动 `cd 最终版 && start_all.bat` 运行，错误信息会停留在窗口。

## 2. 端口 8083 被占用

```bat
netstat -ano | findstr ":8083 " | findstr "LISTENING"
```

按 PID kill：`taskkill /pid <PID> /f`，或直接运行 `stop_all.bat`。脚本启动前会检测并提示，可选继续或取消。

## 3. 后端启动失败：ModuleNotFoundError

后端依赖未装。手动安装：

```bat
cd backend
python -m pip install -r requirements.txt
```

依赖：`flask flask-sock paho-mqtt`。

## 4. 前端页面显示"前端尚未构建"

`frontend/dist/index.html` 不存在。两种处理：
- 生产访问：`cd frontend && npm install && npm run build`
- 开发访问：`start_all.bat` 选 Dev Mode，访问 `http://localhost:5173`（dist 不存在也能跑）

## 5. 没有硬件，大屏怎么有数据？

模拟器模式（菜单 1/3/4）注入 `DAY102_FORCE_FAKE=1`，启动 `backend/bridge/fake_bridge.py` 直接向 SQLite 写模拟数据：温度/湿度随机游走、人体翻转、约 120s 一次异常冲高（温度→37 或烟雾→62）、随机 75s 断网。全程无需 ESP32/MQTT。

## 6. 实物模式启动了 FakeBridge，不是真实 Bridge

`bridge_runner.choose_and_start` 优先级：`DAY102_FORCE_FAKE=1` → MQTT 可达用真实 Bridge → 不可达回退 FakeBridge。

排查：硬件模式（菜单 2）设 `DAY102_FORCE_FAKE=0`，若仍走 FakeBridge，说明 MQTT 不可达：
- 检查 `firmware/config.json` 的 `mqtt_host`/`mqtt_port`（默认 172.16.4.211:9783）
- 用 `telnet 172.16.4.211 9783` 或 TCP 探测确认网络可达
- 内网外部署时改成本机/同网段 broker

## 7. JetLinks 平台残留"在线"会话（僵尸会话）

ESP32 异常断网时 MQTT 未必发遗嘱，平台侧可能残留在线设备。本项目 Web 端已用 `kick_user_sessions` 在用户重新登录时踢掉旧会话；设备侧需在 ESP32 重连后重新上报，或在平台手动踢除。

## 8. 在线率显示 0/8 或偏低

在线判定：`device_status` 中 `updated_at >= now - 60s` 的通道数 ÷ 8。

- **0/8**：数据源未启动或全断网。查 `logs/fake_bridge.log` 或 `logs/bridge.log` 是否有 tick 输出。
- **部分离线**：FakeBridge 每 ~80s 随机让一个传感器断网 75s（>60s 阈值），大屏会显示该通道离线，恢复后自动回到 8/8。属正常演示行为。
- **继电器离线**：继电器由场景规则/用户控制，FakeBridge 每 tick 都写，不应离线；若离线说明 bridge 未写 relay key。

## 9. trigger_count 重启后清零了吗？

不会。`scene_rules.trigger_count` 持久化在 SQLite，Bridge 重启、整机重启都不清零。稳定计数（`last_observed_value/count`）也已入库，重启后首次评估不会被跳过。

## 10. 场景规则不触发

按 `db.evaluate_scene_rules` 四层防护依次排查：
1. **稳定计数**：连续 2 次相同值才触发（`STABLE_THRESHOLD=2`）。值在抖动会被跳过。
2. **冷却时间**：`cooldown_sec` 内不重复触发（默认高温 60s、烟雾 30s、人感 10s）。
3. **条件评估**：`trigger_operator` + `trigger_value` 是否匹配当前值。
4. **动作互斥**：critical（全关）会锁定 info（开灯）动作。

排查：查 `logs/fake_bridge.log` 的 `[fake][告警]` 行，或 GET `/api/scene-rules` 看 `trigger_count` 是否增长。

## 11. 大屏不实时更新

- WebSocket 未连：按 `R` 重连；查浏览器控制台 `ws://localhost:8083/ws/dashboard` 状态。
- 后端 DataWatcher 线程异常：查 `logs/day102.log` 是否有 `[watcher]` 启动行。
- device_status 节流 1.5s：变化后最多 1.5s 推送，非即时。

## 12. 登录后管理页 401/403

- **401 未登录**：cookie 未带或 session 过期（8 小时）。重新登录。
- **403 权限不足**：当前用户不是 admin。用 `admin/admin123` 登录。
- 跨域/反代场景：确保 `Host` 头透传，Cookie `SameSite=Lax`。

## 13. 修改 config.json 后 ESP32 不生效

`config.json` 由 `app_config.py` 在启动时读入内存，修改后需重启 ESP32（断电重插或按 RST）。Web 端 `/api/config-points` 保存后也会提示"ESP32 需重启生效"。

## 14. 数据库锁 "database is locked"

SQLite WAL + `busy_timeout=5000` + `synchronous=NORMAL` 已抑制绝大多数锁冲突。若仍出现：
- 确认没有外部进程长时间持有写事务
- 检查是否有多个 `app.py` 同时跑（同一库）
- 重启后端清理连接

## 15. e2e 测试失败

```bat
python -m pytest tests\e2e\ -v
```

前提：后端在 8083 运行且为模拟器模式（`DAY102_FORCE_FAKE=1`）。8 步覆盖 overview/device-status/scene-rules/alarm-stats/login/me/toggle/clear-all。若某步超时，确认后端已起来：`curl http://localhost:8083/api/overview`。

## 16. Modbus 采集不到传感器值

- 确认从站 `192.168.20.59:5502`（unit_id=7）已运行（可用 `tools/modbus_slave_sim.py` 起本地从站）
- 用 `tools/set_modbus.py` 手动写寄存器验证地址映射（温度 addr0、湿度 addr1、人体 addr4、烟雾 addr5）
- `tools/detect_com.py` 检测可用串口/网络

## 17. 怎么彻底重置数据？

```bat
start_all.bat
:: 选 6 Clean Database —— 先 kill 8083，再删 iot_platform.db* 三个文件
:: 下次启动自动建表 + 预填充 8 路由 + 2 用户 + 4 规则
```

## 18. pip install 拉到 pymodbus 新版本，测试全挂

**现象**：`pip install -r requirements-dev.txt` 后跑 pytest，22 个测试报 `ModbusTcpClient.__init__() takes 2 positional arguments but N were given`。

**根因**：pymodbus 3.15.x 改了构造函数签名——位置参数 `host, port` 改为关键字参数 `host=..., port=...`。项目旧测试用 `ModbusTcpClient(host, port, timeout=2)` 直接挂。

**解决**：`requirements-dev.txt` 已精确锁定 `pymodbus==3.6.9`，不要升级：
```bat
pip install pymodbus==3.6.9 --index-url https://pypi.org/simple/
```

## 19. 告警面板越拉越长，场景联动被挤没

**根因**：FakeBridge 每秒触发提示级规则（有人自动开灯/无人自动关灯），告警列表不断 unshift 新条目，旧前端只设了 20 条上限。

**修复**（已内置）：
- 前端 store 硬上限 **5 条**：`dashboard.js` 中 `while (this.recentAlarms.length > 5) { this.recentAlarms.pop() }`
- REST 首屏拉 `limit=5`：`api.recentAlarms(5)`
- CSS `.alarm-list` 加 `max-height: 200px`：超过 5 条时面板内滚动，不撑开容器

新告警从顶部弹入，最旧的从底部滑出，面板高度恒定。

## 20. e2e 测试首轮 SQLite "attempt to write a readonly database"

**根因**：前一轮 e2e 的 teardown 只调用 `proc.terminate()`（Flask PID），`bridge_runner.start()` 启动的 `fake_bridge.py` 子进程变成孤儿，继续持有 SQLite WAL 锁。下一轮 e2e 启动新 Flask 时，WAL 文件被孤儿进程独占。

**修复**（已内置）：`tests/e2e/conftest.py` teardown 两步杀：
1. **主杀**：`taskkill /pid <Flask_PID> /T /F` — 杀掉 Flask + 所有子进程（包括 bridge）
2. **精确兜底**：从 Flask stdout 解析 bridge PID（`bridge_runner.py` 第 53 行 `print("pid=NNN")`），定向 `taskkill /pid <bridge_pid> /F`。比 PowerShell CIM 扫描全进程快 10 倍以上，且只杀自己的 bridge，不会误伤其他 demo

**为何不用 CIM/wmic 扫全进程**：CIM 查所有 Python 的 CommandLine 需 2-3 秒；且全局扫描会在"跑 e2e 时另一个演示 backend 正在跑"的情况下把演示用 bridge 一起杀掉。定向 PID 是更精准无副作用的方案。

**验证**：连续跑两轮 `pytest tests/e2e/ -v`，两轮都应 8/8 通过（第二轮不应该有上一轮遗留的孤儿）。

相关文档：[01-快速开始](01-quickstart.md) ｜ [05-部署指南](05-deploy.md) ｜ [02-架构设计](02-architecture.md)
