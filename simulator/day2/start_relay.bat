@echo off
chcp 65001 >nul 2>&1
title Relay Simulator - JetLinks
echo ========================================
echo   8-Channel Relay Simulator
echo   JetLinks Direct Connect
echo   Product: relay-cc  Device: relaycc
echo   Ctrl+C to exit
echo ========================================
echo.
cd /d "%~dp0"
if exist relay_data.json del /q relay_data.json
python relay_simulator_jl.py
pause
