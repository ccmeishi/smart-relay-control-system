@echo off
title Modbus TCP 从站模拟器 (unit_id=7)
echo ========================================
echo   Modbus TCP 从站模拟器 - 7组
echo   8路继电器 + 温湿度 + 电流电压
echo   unit_id=7, 端口 5502
echo   Ctrl+C 退出
echo ========================================
echo.
cd /d "%~dp0"
python modbus_slave_sim.py
pause
