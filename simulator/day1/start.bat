@echo off
setlocal enabledelayedexpansion
title Day1 - Sensor Simulator Modbus TCP Slave
echo ========================================
echo   Day1 温湿度模拟器
echo   Modbus TCP 从站  端口 5502  地址 7
echo   Ctrl+C 退出
echo ========================================
echo.

set OCCUPY_PID=
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /C:":5502 " ^| findstr "LISTENING"') do set OCCUPY_PID=%%P
if not "!OCCUPY_PID!"=="" (
    set OCCUPY_NAME=
    for /f "skip=3 tokens=1" %%N in ('tasklist /fi "PID eq !OCCUPY_PID!" 2^>nul') do set OCCUPY_NAME=%%N
    echo [警告] 端口 5502 已被占用: !OCCUPY_NAME!  PID=!OCCUPY_PID!
    echo   通常是上次模拟器进程还在后台, 不是 ESP32 实物
    echo   实物是 Modbus 客户端, 只连出不会占用端口
    echo   强制结束旧进程: taskkill /F /PID !OCCUPY_PID!
    echo.
    choice /C YN /M "仍然启动"
    if !errorlevel!==2 exit /b 1
)

cd /d "%~dp0"
python sensor_simulator.py
pause
