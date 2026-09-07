@echo off
chcp 65001 >nul 2>&1
REM ============================================================
REM  ESP32 串口日志监控启动脚本
REM  双击运行即可，自动查找 COM 口并连接
REM  波特率 115200，按 Ctrl+C 退出
REM ============================================================

echo.
echo ============================================
echo   ESP32 串口日志监控
echo ============================================
echo.

REM 自动检测可用的 COM 口
set PORT=
for /f "tokens=4 delims= " %%P in ('mode 2^>nul ^| findstr "COM"') do (
    if "!PORT!"=="" set PORT=%%P
)

if "%PORT%"=="" (
    echo [错误] 未检测到 COM 口，请确认 ESP32 已连接
    pause
    exit /b 1
)

echo 检测到串口: %PORT%
echo 波特率:     115200
echo.
echo 正在连接... 按 Ctrl+C 退出
echo --------------------------------------------
echo.

python -m serial.tools.miniterm %PORT% 115200 --rts 0 --dtr 0

pause
