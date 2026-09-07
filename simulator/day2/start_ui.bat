@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Day2 - Relay Web UI
echo ========================================
echo   Day2 继电器 Web UI
echo   浏览器访问: http://localhost:8081
echo   Ctrl+C 退出
echo ========================================
echo.

REM 检查 8081 端口
netstat -ano | findstr ":8081 " | findstr "LISTENING" >nul
if !errorlevel!==0 (
    echo [警告] 端口 8081 已被占用, Web UI 可能已在运行
    choice /C YN /M "仍然启动"
    if !errorlevel!==2 exit /b 1
)

cd /d "%~dp0"
echo 启动后请手动打开浏览器访问 http://localhost:8081
echo.
start "" http://localhost:8081
python relay_ui.py
pause