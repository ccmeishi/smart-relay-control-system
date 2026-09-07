@echo off
setlocal enabledelayedexpansion
title Day2 - Sensor Simulator JetLinks
echo ========================================
echo   Day2 温湿度模拟器 JetLinks 格式
echo   Ctrl+C 退出
echo ========================================
echo.
cd /d "%~dp0"
if exist sensor_data.json del /q sensor_data.json
python sensor_simulator_jl.py
pause
