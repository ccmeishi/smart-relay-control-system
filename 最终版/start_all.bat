@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Smart Relay Control System - Launcher
cd /d "%~dp0"

:MENU
cls
echo ============================================================
echo   Smart Relay Control System - Integrated Edition
echo ============================================================
echo.
echo   [1] Start - Simulator Mode  - recommended, no hardware
echo   [2] Start - Hardware Mode   - needs ESP32 + MQTT broker
echo   [3] Start - Dev Mode        - frontend hot reload on :5173
echo   [4] Start - Backend Only   - no browser auto-open
echo   [5] Run Tests               - pytest
echo   [6] Clean Database          - delete iot_platform.db
echo   [7] Exit
echo.
set /p choice=Select:

if "!choice!"=="1" goto MODE_SIM
if "!choice!"=="2" goto MODE_HW
if "!choice!"=="3" goto MODE_DEV
if "!choice!"=="4" goto MODE_BK
if "!choice!"=="5" goto RUN_TESTS
if "!choice!"=="6" goto CLEAN_DB
if "!choice!"=="7" goto END
echo [ERROR] Invalid choice.
timeout /t 2 >nul
goto MENU

REM ============================================================
REM Mode presets
REM ============================================================
:MODE_SIM
set DAY102_FORCE_FAKE=1
set OPEN_BROWSER=1
set DEV_MODE=0
goto COMMON_CHECKS

:MODE_HW
set DAY102_FORCE_FAKE=0
set OPEN_BROWSER=1
set DEV_MODE=0
goto COMMON_CHECKS

:MODE_DEV
set DAY102_FORCE_FAKE=1
set OPEN_BROWSER=1
set DEV_MODE=1
goto COMMON_CHECKS

:MODE_BK
set DAY102_FORCE_FAKE=1
set OPEN_BROWSER=0
set DEV_MODE=0
goto COMMON_CHECKS

REM ============================================================
REM Common pre-checks: Python, deps, port, frontend dist
REM ============================================================
:COMMON_CHECKS
echo.
echo [Check] Step 1/4 - Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ and add to PATH.
    pause
    goto END
)
python -c "import sys; print('  Python', sys.version.split()[0])"

echo [Check] Step 2/4 - Backend dependencies...
python -c "import flask, flask_sock, paho.mqtt" >nul 2>&1
if errorlevel 1 (
    echo [WARN] Missing dependencies, installing from backend/requirements.txt ...
    python -m pip install -r backend\requirements.txt
    if errorlevel 1 (
        echo [ERROR] pip install failed. Run manually:
        echo         pip install -r backend\requirements.txt
        pause
        goto END
    )
) else (
    echo        OK - flask, flask-sock, paho-mqtt
)

echo [Check] Step 3/4 - Port 8083...
netstat -ano | findstr ":8083 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [WARN] Port 8083 is already in use. Backend may already be running.
    echo        Run stop_all.bat first, or continue anyway.
    choice /c YN /m "Continue anyway Y=Yes N=No"
    if errorlevel 2 (
        echo [Info] Cancelled by user.
        pause
        goto MENU
    )
) else (
    echo        OK - port 8083 is free
)

echo [Check] Step 4/4 - Frontend build...
if not exist "frontend\dist\index.html" (
    echo [Build] Frontend dist not found, building now - needs Node 18+...
    where node >nul 2>&1
    if errorlevel 1 (
        echo [ERROR] Node.js not found. Install Node 18+, then run manually:
        echo           cd frontend ^&^& npm install ^&^& npm run build
        pause
        goto END
    )
    pushd frontend
    call npm install
    if errorlevel 1 (
        echo [ERROR] npm install failed.
        popd
        pause
        goto END
    )
    call npm run build
    if errorlevel 1 (
        echo [ERROR] npm run build failed.
        popd
        pause
        goto END
    )
    popd
    echo [Build] Frontend build completed.
) else (
    echo        OK - frontend/dist/index.html exists
)

REM ============================================================
REM Start backend
REM ============================================================
echo.
echo [Start] Backend on port 8083 - data source monitor included...
start "IoT-Backend" cmd /k "cd /d %~dp0backend && set DAY102_FORCE_FAKE=%DAY102_FORCE_FAKE% && python app.py"

REM ============================================================
REM Dev mode: also start npm run dev
REM ============================================================
if "!DEV_MODE!"=="1" (
    echo [Start] Frontend dev server on port 5173 - hot reload...
    timeout /t 2 /nobreak >nul
    start "IoT-Frontend-Dev" cmd /k "cd /d %~dp0frontend && npm run dev"
    echo [Wait] Opening dev server in 8 seconds...
    timeout /t 8 /nobreak >nul
    start "" "http://localhost:5173"
    goto SHOW_INFO
)

echo [Wait] Opening dashboard in 8 seconds...
timeout /t 8 /nobreak >nul
if "!OPEN_BROWSER!"=="1" start "" "http://localhost:8083"

:SHOW_INFO
echo.
echo ============================================================
echo   Service started successfully!
echo ============================================================
echo.
echo   Dashboard URL : http://localhost:8083
echo   REST API      : http://localhost:8083/api/overview
echo   WebSocket     : ws://localhost:8083/ws/dashboard
echo   Admin login   : http://localhost:8083/login  -  admin / admin123
echo.
if "!DEV_MODE!"=="1" echo   Dev server    : http://localhost:5173
echo.
echo   Data source:
if "!DAY102_FORCE_FAKE!"=="1" echo     Simulator mode - FakeBridge simulated data
if "!DAY102_FORCE_FAKE!"=="0" echo     Hardware mode  - real ESP32 via MQTT auto-detect
echo.
echo   Keyboard shortcuts on dashboard:
echo     F = fullscreen   Esc = exit fullscreen   R = reconnect WebSocket
echo.
echo   To stop: close the backend window or run stop_all.bat
echo ============================================================
echo.
pause
goto END

REM ============================================================
REM Run pytest
REM ============================================================
:RUN_TESTS
echo.
echo [Test] Checking Python...
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found.
    pause
    goto MENU
)
echo [Test] Running pytest in tests/ directory...
python -m pytest tests\ -v --tb=short
echo.
echo [Test] Done. See results above.
pause
goto MENU

REM ============================================================
REM Clean database
REM ============================================================
:CLEAN_DB
echo.
echo [WARN] This will delete the database. All data - alarms, rules, users - will be lost.
choice /c YN /m "Are you sure Y=Yes delete N=No cancel"
if errorlevel 2 (
    echo [Info] Cancelled.
    pause
    goto MENU
)
echo [Clean] Stopping backend first...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8083 " ^| findstr "LISTENING"') do (
    taskkill /pid %%a /f >nul 2>&1
)
timeout /t 2 /nobreak >nul
echo [Clean] Deleting database files...
if exist "iot_platform.db" del /q "iot_platform.db"
if exist "iot_platform.db-wal" del /q "iot_platform.db-wal"
if exist "iot_platform.db-shm" del /q "iot_platform.db-shm"
echo [Clean] Done. A fresh database will be created on next start.
pause
goto MENU

:END
echo Goodbye.
