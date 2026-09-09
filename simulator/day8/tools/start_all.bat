@echo off
chcp 65001 >nul 2>&1
title IoT Gateway - Start All

echo ========================================
echo   ESP32 Modbus Gateway + Bridge Start
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found
    pause
    exit /b 1
)

cd /d "%~dp0"

echo [1/2] Starting Modbus TCP Slave Simulator (port 5502, unit_id=7)...
start "ModbusSim" cmd /k "python -u modbus_slave_sim.py 5502 7"

timeout /t 2 /nobreak >nul

echo [2/2] Starting Python Bridge...
start "Bridge" cmd /k "python -u gateway_bridge.py"

echo.
echo ========================================
echo   Done!
echo ========================================
echo.
echo   Modbus Simulator: 0.0.0.0:5502 (unit_id=7)
echo   Bridge: subscribe relay-cc/relaycc/# 
echo.
echo   Usage:
echo     python set_modbus.py 25 60 1 50
echo     python set_modbus.py --human 0
echo.
echo   Close the two popup windows to stop.
echo.
pause
