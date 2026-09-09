@echo off
setlocal enabledelayedexpansion
title ESP32 Serial Monitor
echo ========================================
echo   ESP32 串口日志监控
echo   波特率 115200  Ctrl+C 退出
echo ========================================
echo.

set PORT=
set /p PORT=请输入 COM 编号  直接回车自动检测:
if "!PORT!"=="" (
    echo.
    echo 正在自动探测 ESP32 COM 口...
    for /f "usebackq delims=" %%N in (`python "%~dp0..\tools\detect_com.py"`) do set PORT=%%N
    if "!PORT!"=="" (
        echo [错误] 未检测到 COM 口
        echo   请确认 ESP32 已连接 USB 线
        echo   或手动输入 COM 编号如 5
        pause & exit /b 1
    )
    echo 检测到 COM!PORT!
)

echo.
echo === 开始监控 COM!PORT! ===
python -m serial.tools.miniterm COM!PORT! 115200 --rts 0 --dtr 0
echo.
echo === 监控结束 ===
pause
