@echo off
chcp 65001 >nul 2>&1
title Relay Web UI - Control Console
echo ========================================
echo   Relay Web UI Console
echo   MQTT Link + Direct Modbus
echo   http://127.0.0.1:8081
echo   Ctrl+C to exit
echo ========================================
echo.
cd /d "%~dp0"
python relay_ui.py
pause
