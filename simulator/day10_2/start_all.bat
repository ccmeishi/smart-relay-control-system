@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Day10.2 IoT Dashboard - Start All
cd /d "%~dp0"

echo ============================================================
echo   Day10.2 Smart IoT Dashboard
echo   Vue3 + ECharts + WebSocket + Flask + MQTT Bridge
echo ============================================================
echo.

REM ---- 1. Check Python ----
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ and add to PATH.
    pause
    exit /b 1
)

REM ---- 2. Check backend dependencies ----
echo [Check] Verifying backend dependencies (flask, flask-sock, paho-mqtt)...
python -c "import flask, flask_sock, paho.mqtt" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Missing dependencies, installing flask flask-sock paho-mqtt ...
    python -m pip install flask flask-sock paho-mqtt
    if errorlevel 1 (
        echo [ERROR] pip install failed. Please run manually:
        echo         pip install flask flask-sock paho-mqtt
        pause
        exit /b 1
    )
)

REM ---- 3. Port conflict check (8083) ----
echo [Check] Checking port 8083 (Dashboard backend)...
netstat -ano | findstr ":8083 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [WARN] Port 8083 is already in use. Dashboard backend may already be running.
    echo        Close the old backend window first if you want to restart.
    choice /c YN /m "Continue anyway - Y to start, N to cancel"
    if errorlevel 2 (
        echo [Info] User cancelled. Exiting.
        pause
        exit /b 0
    )
)

REM ---- 4. Check frontend build, build automatically if missing ----
if not exist "frontend\dist\index.html" (
    echo [Build] Frontend dist not found, building now - requires Node 18+ on first run...
    where node >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Node.js not found, cannot build frontend.
        echo         Install Node 18+ then run manually:
        echo            cd frontend
        echo            npm install
        echo            npm run build
        pause
        exit /b 1
    )
    pushd frontend
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        popd
        pause
        exit /b 1
    )
    call npm run build
    if errorlevel 1 (
        echo [ERROR] npm run build failed.
        popd
        pause
        exit /b 1
    )
    popd
    echo [Build] Frontend build completed.
)

REM ---- 5. Start backend (auto-selects real Bridge or FakeBridge) ----
echo.
echo [Start] Backend service on port 8083 (data source monitor included)...
start "Day10.2-Backend" cmd /k "cd /d %~dp0backend && python app.py"

REM ---- 6. Wait for backend, then open browser ----
echo [Wait] Opening dashboard in 8 seconds...
timeout /t 8 /nobreak >nul
start "" "http://localhost:8083"

echo.
echo ============================================================
echo   Dashboard started!
echo ============================================================
echo.
echo   Dashboard URL : http://localhost:8083
echo   REST API      : http://localhost:8083/api/overview
echo   WebSocket     : ws://localhost:8083/ws/dashboard
echo.
echo   Data source:
echo     * MQTT reachable  -^> Real Bridge (ESP32 -^> EMQX -^> Dashboard)
echo     * MQTT unreachable -^> FakeBridge simulated data (demo still works)
echo.
echo   Frontend dev mode (hot reload), open another window and run:
echo     cd frontend
echo     npm run dev    ^(visit http://localhost:5173^)
echo.
echo   Keyboard shortcuts on dashboard:
echo     F = fullscreen,  Esc = exit fullscreen,  R = reconnect WebSocket
echo.
echo   Close the popup backend window to stop the service.
echo ============================================================
echo.
pause
