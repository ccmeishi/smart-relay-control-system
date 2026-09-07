@echo off
chcp 65001 >nul 2>&1
title Day7 - Modbus TCP Slave Simulator (PC端)
echo ========================================
echo   Day7 Modbus TCP 从站模拟器
echo   用于测试 ESP32 Modbus 网关采集
echo   端口: 5502  从站地址: 7
echo   寄存器: reg0=温度, reg1=湿度
echo   Ctrl+C 退出
echo ========================================
echo.
cd /d "%~dp0\..\tools"
python modbus_slave_sim.py 5502 7
pause
