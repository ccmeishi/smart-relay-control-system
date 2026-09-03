@echo off
chcp 65001 >nul 2>&1
title Modbus TCP Slave (unit_id=7)
echo ========================================
echo   Modbus TCP Slave Simulator - Group 7
echo   8 relays + temp/humidity + current/voltage
echo   unit_id=7, port 5502
echo   Ctrl+C to exit
echo ========================================
echo.
cd /d "%~dp0"
python modbus_slave_sim.py 7
pause
