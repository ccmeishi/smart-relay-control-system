@echo off
title 温湿度传感器模拟器 - JetLinks直连
echo ========================================
echo   温湿度传感器模拟器
echo   JetLinks 直连 (方式二)
echo   产品: sensor-cc  设备: sensorcc
echo   Ctrl+C 退出
echo ========================================
echo.
cd /d "%~dp0"
if exist sensor_data.json del sensor_data.json
echo 已清理 sensor_data.json 缓存
python sensor_simulator_jl.py
pause
