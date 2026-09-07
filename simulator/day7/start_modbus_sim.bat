@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Day7 - Modbus TCP 从站模拟器
echo ========================================
echo   Day7 Modbus TCP 从站模拟器 PC端
echo   用于测试 ESP32 Modbus 网关采集
echo   端口: 5502  从站地址: 7
echo   Ctrl+C 退出
echo ========================================
echo.

netstat -ano | findstr ":5502 " | findstr "LISTENING" >nul
if !errorlevel!==0 (
    echo [警告] 端口 5502 已被占用
    echo   可能 Day1 模拟器已在运行, 两者互斥
    echo.
    choice /C YN /M "仍然启动"
    if !errorlevel!==2 exit /b 1
)

cd /d "%~dp0\..\tools"
python modbus_slave_sim.py 5502 7
pause
