# 01 - 快速开始

## 一、环境准备

| 依赖 | 版本 | 用途 |
|------|------|------|
| Python | 3.10+ | 后端 + 测试 |
| Node.js | 18+ | 前端构建（dist 已提交则非必需） |
| pip 包 | flask flask-sock paho-mqtt | 后端运行 |

> Windows 用户直接双击 `start_all.bat`，脚本会自动检测 Python、缺失依赖、端口占用、前端 dist 是否已构建，并按需补装。

## 二、模拟器模式（5 分钟上手，推荐）

无需任何硬件，FakeBridge 自动模拟数据飘动 + 异常冲高 + 随机断网，可完整演示大屏联动与告警。

```bat
cd 最终版
start_all.bat
```

菜单输入 `1` 选择 Simulator Mode，脚本依次完成：

1. 检测 Python 版本
2. 缺失依赖自动 `pip install -r backend\requirements.txt`
3. 检测 8083 端口是否被占用（占用会提示）
4. `frontend\dist\index.html` 不存在则自动 `npm install && npm run build`
5. 新窗口启动后端：`python app.py`（注入 `DAY102_FORCE_FAKE=1`）
6. 8 秒后自动打开 `http://localhost:8083`

大屏渲染后即可看到温度/湿度折线滚动、人体感应翻转、约 120s 一次的异常冲高触发 critical 告警与全关继电器。

## 三、实物模式（需 ESP32 + MQTT broker）

前置条件：

- ESP32-C3 已刷入 `firmware/` 固件（MicroPython v1.29.0）
- 首次上电进入热点 `RELAY-SETUP-xxxx`，手机连 `192.168.4.1` 配置 WiFi + MQTT
- `firmware/config.json` 中 `mqtt_host` 指向可达的 EMQX/JetLinks（默认 172.16.4.211:9783）
- Modbus 从站 `192.168.20.59:5502`（unit_id=7）已运行

```bat
start_all.bat
:: 菜单输入 2 选择 Hardware Mode
```

此模式注入 `DAY102_FORCE_FAKE=0`，`bridge_runner.py` 会先 TCP 探测 MQTT broker：
- 可达 → 启动 `bridge/gateway_bridge.py`（真实 ESP32 数据）
- 不可达 → 自动回退 FakeBridge，保证大屏不空白

## 四、开发模式（前端热重载）

前端用 Vite dev server，改动 Vue 文件即时生效：

```bat
start_all.bat
:: 菜单输入 3 选择 Dev Mode
```

- 后端：http://localhost:8083（Flask）
- 前端：http://localhost:5173（Vite 热重载，`vite.config.js` 已配 `/api` 与 `/ws` 代理到 8083）

> Dev Mode 同样注入 `DAY102_FORCE_FAKE=1`，所以即便无硬件也有模拟数据。

## 五、后端独立启动（不开浏览器）

```bat
start_all.bat
:: 菜单输入 4 选择 Backend Only
```

仅启动后端进程，不自动开浏览器，适合调试 API 或跑测试。

## 六、手动启动（不走 bat）

```bat
:: 后端
cd backend
set DAY102_FORCE_FAKE=1
python app.py

:: 前端开发（另一窗口）
cd frontend
npm install
npm run dev
```

## 七、运行测试

```bat
:: e2e 全链路（8 步，使用模拟器模式）
python -m pytest tests\e2e\ -v

:: 全部测试
pip install -r requirements-dev.txt
python -m pytest tests\ -v
```

## 八、停止服务

双击 `stop_all.bat`，自动 kill 8083/5173 端口进程及 `IoT-Backend`/`IoT-Frontend-Dev` 窗口。

> 也可直接关闭后端命令行窗口，子进程随之退出。

相关文档：[00-项目概述](00-overview.md) ｜ [05-部署指南](05-deploy.md) ｜ [06-常见问题](06-faq.md)
