@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d %~dp0

echo ============================================================
echo   Day10.2 智慧物联网大屏 (Vue3 + ECharts + WebSocket)
echo ============================================================

REM ---- 1. 检测 Python ----
python --version >nul 2>&1
if errorlevel 1 (
    echo [X] 未检测到 Python, 请先安装 Python 3.10+
    pause & exit /b 1
)

REM ---- 2. 检测关键依赖库 ----
python -c "import flask, flask_sock, paho.mqtt" >nul 2>&1
if errorlevel 1 (
    echo [!] 缺少后端依赖, 正在安装 flask flask-sock paho-mqtt ...
    python -m pip install flask flask-sock paho-mqtt
)

REM ---- 3. 端口冲突检测 (8083) ----
netstat -ano | findstr ":8083 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [!] 端口 8083 已被占用, 大屏后端可能已在运行
    echo     如需重启请先关闭占用 8083 的窗口
    choice /c YN /m "是否仍要继续"
    if errorlevel 2 exit /b 0
)

REM ---- 4. 检测前端构建产物, 缺失则自动构建 ----
if not exist "frontend\dist\index.html" (
    echo [!] 未检测到前端构建产物, 开始构建 (首次需要 Node 18+)...
    where node >nul 2>&1
    if errorlevel 1 (
        echo [X] 未检测到 Node.js, 无法构建前端
        echo     请安装 Node 18+ 后执行: cd frontend ^&^& npm install ^&^& npm run build
        pause & exit /b 1
    )
    pushd frontend
    call npm install
    call npm run build
    popd
)

REM ---- 5. 启动后端 (自动选择真实 Bridge 或 FakeBridge) ----
echo [启动] 后端服务 (端口 8083, 内含数据源进程监控)...
start "Day10.2-Backend" cmd /k "cd /d %~dp0backend && python app.py"

REM ---- 6. 等待后端就绪后打开浏览器 ----
echo [等待] 8 秒后打开大屏...
timeout /t 8 /nobreak >nul
start http://localhost:8083

echo.
echo ============================================================
echo   大屏已启动!
echo   - 大屏地址:   http://localhost:8083
echo   - REST API:  http://localhost:8083/api/overview
echo   - WebSocket: ws://localhost:8083/ws/dashboard
echo.
echo   数据源:
echo     * MQTT 可达  -^> 真实 Bridge (ESP32 -> EMQX -> 大屏)
echo     * MQTT 不可达 -^> FakeBridge 模拟数据 (大屏仍可演示)
echo.
echo   前端开发模式 (热更新): 另开窗口执行
echo     cd frontend ^&^& npm run dev  ^(访问 http://localhost:5173^)
echo ============================================================
pause
