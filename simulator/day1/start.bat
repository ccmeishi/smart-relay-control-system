@echo off
setlocal enabledelayedexpansion
title Day1 - Sensor Simulator Modbus TCP Slave
echo ========================================
echo   Day1 温湿度模拟器
echo   Modbus TCP 从站
echo   端口: 5502  从站地址: 7
echo   Ctrl+C 退出
echo ========================================
echo.

netstat -ano | findstr ":5502 " | findstr "LISTENING" >nul
if !errorlevel!==0 (
    echo [警告] 端口 5502 已被占用
    echo   建议: 先关掉其他模拟器窗口再启动
    echo.
    choice /C YN /M "仍然启动"
    if !errorlevel!==2 exit /b 1
)

cd /d "%~dp0"
python sensor_simulator.py
pause
