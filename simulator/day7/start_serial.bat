@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title ESP32 - 串口日志监控
echo ========================================
echo   ESP32 串口日志监控
echo   波特率: 115200
echo   Ctrl+C 退出
echo ========================================
echo.

set PORT=
set /p PORT=请输入 COM 口 (直接回车自动检测):
if "!PORT!"=="" (
    for /f "tokens=4 delims= " %%P in ('mode 2^>nul ^| findstr /i "COM"') do (
        if "!PORT!"=="" set PORT=%%P
    )
)

if "!PORT!"=="" (
    echo [错误] 未检测到 COM 口, 请确认 ESP32 已连接
    pause
    exit /b 1
)

echo 使用串口: !PORT!
echo.
python -m serial.tools.miniterm !PORT! 115200 --rts 0 --dtr 0
pause