@echo off
setlocal enabledelayedexpansion
title Day1 - Sensor Simulator Modbus TCP Slave
echo ========================================
echo   Day1 temperature-humidity simulator
echo   Modbus TCP slave  port 5502  unit 7
echo   Ctrl+C to exit
echo ========================================
echo.

set OCCUPY_PID=
for /f "tokens=5" %%P in ('netstat -ano ^| findstr /C:":5502 " ^| findstr "LISTENING"') do set OCCUPY_PID=%%P
if not "!OCCUPY_PID!"=="" (
    set OCCUPY_NAME=
    for /f "skip=3 tokens=1" %%N in ('tasklist /fi "PID eq !OCCUPY_PID!" 2^>nul') do set OCCUPY_NAME=%%N
    echo [WARNING] port 5502 in use: !OCCUPY_NAME!  PID=!OCCUPY_PID!
    echo   kill old process: taskkill /F /PID !OCCUPY_PID!
    echo.
    choice /C YN /M "continue anyway"
    if !errorlevel!==2 exit /b 1
)

cd /d "%~dp0"
python sensor_simulator.py
pause
