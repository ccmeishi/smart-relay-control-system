@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Day10 IoT Platform - Start All

echo ========================================
echo   Day10 IoT Management Platform
echo   Modbus + Bridge + Web GUI + Scene + Alarm
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+ and add to PATH.
    pause
    exit /b 1
)

python -c "import flask, paho.mqtt.client, serial, pymodbus" 2>nul
if errorlevel 1 (
    echo [ERROR] Missing dependencies. Run:
    echo         pip install -r requirements.txt
    pause
    exit /b 1
)

cd /d "%~dp0"

:: --- Port conflict check ---
echo [Check] Checking port 5502 (Modbus Slave)...
netstat -ano | findstr ":5502 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [WARN] Port 5502 is already in use. Modbus simulator may fail.
    echo        Close the old simulator or another program using this port.
    pause
)

echo [Check] Checking port 8081 (Web GUI)...
netstat -ano | findstr ":8081 " | findstr "LISTENING" >nul
if not errorlevel 1 (
    echo [WARN] Port 8081 is already in use. Web GUI may fail.
    echo        Close the old web server or another program using this port.
    pause
)

:: --- Step 0: Init DB (first run) ---
echo.
echo [0/3] Initializing SQLite database...
python db.py
if errorlevel 1 (
    echo [WARN] DB init had issues, but continuing...
)

:: --- Step 1: Modbus Slave Simulator ---
echo.
echo [1/3] Starting Modbus TCP Slave Simulator (port 5502, unit_id=7)...
start "ModbusSim-Day10" cmd /k "python -u modbus_slave_sim.py 5502 7"

timeout /t 2 /nobreak >nul

:: --- Step 2: Bridge (with hot-reload + scene evaluation) ---
echo [2/3] Starting Python Bridge (SQLite routing + scene rules + alarm)...
start "Bridge-Day10" cmd /k "python -u gateway_bridge.py --hot-reload"

timeout /t 2 /nobreak >nul

:: --- Step 3: Web GUI ---
echo [3/3] Starting Web Management GUI on port 8081...
start "Web-Day10" cmd /k "python -u web\app.py"

echo.
echo ========================================
echo   All services started!
echo ========================================
echo.
echo   Modbus Simulator: 0.0.0.0:5502 (unit_id=7)
echo   Bridge: relay-cc/relaycc/# + scene rules + alarm
echo   Web GUI: http://127.0.0.1:8081
echo.
echo   Default login: admin / admin123
echo                 user  / user123
echo.
echo   Day10 New Features:
echo     /scenes  - Scene rule management (IF condition THEN action)
echo     /alarms  - Alarm records (active/acknowledged/cleared)
echo.
echo   Usage:
echo     python set_modbus.py 35 60 1 50   (set temp=35 to trigger alarm)
echo     python set_modbus.py --human 1    (set human=1 to trigger light)
echo.
echo   Close the three popup windows to stop all services.
echo ========================================
echo.
pause
