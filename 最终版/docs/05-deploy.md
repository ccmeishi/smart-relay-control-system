# 05 - 部署指南

## 一、Windows 本地部署（推荐）

最简方式：双击 `start_all.bat`，按菜单选择模式。脚本自动完成依赖检测、端口检查、前端构建与后端启动。

### 前置条件

- Python 3.10+（加入 PATH）
- Node.js 18+（仅当 `frontend/dist` 不存在时需要，用于 `npm run build`）
- 后端依赖：`flask flask-sock paho-mqtt`（缺失时脚本自动 `pip install -r backend\requirements.txt`）

### 端口配置

| 端口 | 服务 | 配置方式 |
|------|------|----------|
| 8083 | Flask 后端 + WS + 前端静态 | 环境变量 `PORT`（默认 8083） |
| 5173 | Vite dev server | 仅 Dev Mode |

改端口示例：

```bat
set PORT=9090
cd backend
python app.py
```

### 目录与数据

- 数据库：`最终版/iot_platform.db`（首次运行自动建表 + 预填充）
- 日志：`最终版/logs/`（`bridge.log` / `fake_bridge.log` / `day102.log`）
- 前端构建产物：`最终版/frontend/dist/`（已提交，免 Node 部署）

### 启动模式速查

| 菜单 | 环境变量 | 数据源 |
|------|----------|--------|
| 1 Simulator | `DAY102_FORCE_FAKE=1` | FakeBridge |
| 2 Hardware | `DAY102_FORCE_FAKE=0` | MQTT 可达→真实 Bridge，不可达→FakeBridge |
| 3 Dev | `DAY102_FORCE_FAKE=1` + `DEV_MODE=1` | FakeBridge + Vite 5173 |
| 4 Backend Only | `DAY102_FORCE_FAKE=1` | FakeBridge，不开浏览器 |

## 二、停止与清理

```bat
:: 停止全部服务
stop_all.bat

:: 删库重建（菜单 6）
start_all.bat  :: 选 6，会先 kill 8083 再删 iot_platform.db*
```

## 三、生产环境建议

本项目以教学为主，生产部署需补充以下措施。

### 1. 安全加固（必做）

- 修改 `app.secret_key`（环境变量 `SECRET_KEY`），不要用默认值
- 改默认 `admin/admin123` 密码（登录后在用户管理页修改）
- `firmware/config.json` 中的 `mqtt_pass`/`wifi_pass` 用真实凭据，勿提交到公开仓库
- 反向代理启用 HTTPS，Cookie 加 `Secure` 标志

### 2. 反向代理（Nginx）

```nginx
server {
    listen 443 ssl;
    server_name iot.example.com;

    location / {
        proxy_pass http://127.0.0.1:8083;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    # WebSocket 升级
    location /ws/ {
        proxy_pass http://127.0.0.1:8083;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 3600s;
    }
}
```

### 3. Linux systemd 守护

```ini
# /etc/systemd/system/iot-backend.service
[Unit]
Description=IoT Smart Relay Backend
After=network.target

[Service]
Type=simple
User=iot
WorkingDirectory=/opt/iot/backend
Environment=PORT=8083
Environment=DAY102_FORCE_FAKE=0
Environment=SECRET_KEY=change-me
ExecStart=/usr/bin/python3 app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now iot-backend
```

Bridge 子进程由 `app.py` 内部管理，无需单独建 service。

### 4. 数据备份

- 定期备份 `iot_platform.db`（WAL 模式下备份主文件即可）
- 历史表 `device_status_history` 自动按 60 分钟清理，无需手动维护

## 四、bat 脚本约束

`start_all.bat` / `stop_all.bat` 遵循 Windows 批处理约束：
- 行尾 CRLF
- 纯 ASCII 英文（含 `chcp 65001` 输出中文需 UTF-8 代码页）
- `if` 块内不使用字面括号 `()`，避免语法错误
- 所有退出路径都带 `pause`，防闪退

修改 bat 时务必遵守上述约束，否则会出现双击闪退（详见 [06-常见问题](06-faq.md)）。

相关文档：[01-快速开始](01-quickstart.md) ｜ [06-常见问题](06-faq.md)
