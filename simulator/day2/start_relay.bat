@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Day2 - Relay Simulator JetLinks
echo ========================================
echo   Day2 继电器模拟器 JetLinks 直连
echo   4 路继电器 + 温湿度采集
echo   Ctrl+C 退出
echo ========================================
echo.
cd /d "%~dp0"

netstat -ano | findstr ":5502 " | findstr "LISTENING" >nul
if !errorlevel! neq 0 (
    echo [提示] 端口 5502 未监听, Day1 温湿度模拟器未启动
    echo   建议: 先双击 day1\start.bat 再启动本脚本
    echo.
)

if exist relay_data.json del /q relay_data.json
python relay_simulator_jl.py
pause
