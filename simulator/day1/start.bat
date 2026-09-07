@echo off
chcp 65001 >nul 2>&1
title Day1 - Sensor Simulator (Modbus TCP Slave)
echo ========================================
echo   Day1 温湿度模拟器
echo   Modbus TCP 从站
echo   端口: 5502  从站地址: 7
echo   Ctrl+C 退出
echo ========================================
echo.
cd /d "%~dp0"
python sensor_simulator.py
pause
