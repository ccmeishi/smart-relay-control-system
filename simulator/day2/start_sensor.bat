@echo off
chcp 65001 >nul 2>&1
title Sensor Simulator - JetLinks
echo ========================================
echo   Temp/Humidity Sensor Simulator
echo   JetLinks Direct Connect
echo   Product: sensor-cc  Device: sensorcc
echo   Ctrl+C to exit
echo ========================================
echo.
cd /d "%~dp0"
if exist sensor_data.json del /q sensor_data.json
python sensor_simulator_jl.py
pause
