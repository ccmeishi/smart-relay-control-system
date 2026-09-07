@echo off
setlocal enabledelayedexpansion
title ESP32-C3 Full Flash + Upload (Day5-Day7 Unified)
echo ========================================
echo   ESP32-C3 一键刷固件 + 上传源码 + Reset
echo   NOTE: close all serial monitor windows first
echo ========================================
echo.

set PORT=
set /p PORT=COM number (default 5):
if "!PORT!"=="" set PORT=5

cd /d "%~dp0"
set "SRC=%~dp0..\esp32"

where python >nul 2>&1 || (echo [ERROR] python not found in PATH & pause & exit /b 1)
where esptool >nul 2>&1 || pip install esptool mpremote pyserial

echo.
echo === [1/4] Erase flash ===
python -m esptool --port COM!PORT! erase-flash
if !errorlevel! neq 0 (echo [ERROR] erase failed & pause & exit /b 1)

echo.
echo === [2/4] Flash MicroPython (esptool v5) ===
python -m esptool --port COM!PORT! --chip esp32c3 --baud 460800 --flash-mode dio --flash-freq 40m write-flash 0x0 "!SRC!\_firmware\ESP32_GENERIC_C3-v1.29.0.bin"
if !errorlevel! neq 0 (echo [ERROR] flash failed & pause & exit /b 1)

echo.
echo === [3/4] Upload source ===
echo   boot.py, main.py, relay_hw.py, app_config.py, ap_config.py, modbus_gw.py
echo   umqtt/simple.py
python -m mpremote connect COM!PORT! cp "!SRC!\boot.py" :/boot.py
python -m mpremote connect COM!PORT! cp "!SRC!\relay_hw.py" :/relay_hw.py
python -m mpremote connect COM!PORT! cp "!SRC!\app_config.py" :/app_config.py
python -m mpremote connect COM!PORT! cp "!SRC!\ap_config.py" :/ap_config.py
python -m mpremote connect COM!PORT! cp "!SRC!\modbus_gw.py" :/modbus_gw.py
python -m mpremote connect COM!PORT! cp "!SRC!\main.py" :/main.py
python -m mpremote connect COM!PORT! mkdir umqtt 2>nul
python -m mpremote connect COM!PORT! cp "!SRC!\umqtt\simple.py" :umqtt\simple.py

echo.
echo === [4/4] Reset ===
python -m mpremote connect COM!PORT! reset

echo.
echo === DONE ===
pause
