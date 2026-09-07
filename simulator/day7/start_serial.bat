@echo off
chcp 65001 >nul 2>&1
title ESP32 - Serial Monitor (自动检测 COM 口)
echo ========================================
echo   ESP32 串口日志监控
echo   波特率: 115200
echo   Ctrl+C 退出
echo ========================================
echo.

REM 自动检测 COM 口
set PORT=
for /f "tokens=4 delims= " %%P in ('mode 2^>nul ^| findstr "COM"') do (
    if "!PORT!"=="" set PORT=%%P
)

if "%PORT%"=="" (
    echo [错误] 未检测到 COM 口, 请确认 ESP32 已连接
    pause
    exit /b 1
)

echo 检测到串口: %PORT%
echo.
python -m serial.tools.miniterm %PORT% 115200 --rts 0 --dtr 0
pause
