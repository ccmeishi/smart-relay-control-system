@echo off
setlocal enabledelayedexpansion
title Day5 ESP32 Full Flash + Upload
echo ========================================
echo   Day5 ESP32 erase + flash + upload + monitor
echo   NOTE: close all serial monitor windows first
echo ========================================
echo.

set PORT=
set /p PORT=COM number (default 5):
if "!PORT!"=="" set PORT=5

cd /d "%~dp0"
set FW_DIR=esp32_firmware

where python >nul 2>&1 || (echo [ERROR] python not found in PATH & pause & exit /b 1)
where esptool >nul 2>&1 || pip install esptool mpremote pyserial

echo.
echo === [1/4] Erase flash ===
python -m esptool --port COM!PORT! erase_flash
if !errorlevel! neq 0 (echo [ERROR] erase failed & pause & exit /b 1)

echo.
echo === [2/4] Flash MicroPython ===
python -m esptool --port COM!PORT! --chip esp32c3 flash_mode dio --flash_freq 40m flash_id !FW_DIR!\_firmware\ESP32_GENERIC_C3-v1.29.0.bin
if !errorlevel! neq 0 (echo [ERROR] flash failed & pause & exit /b 1)

echo.
echo === [3/4] Upload source ===
python -m mpremote connect COM!PORT! cp !FW_DIR!\boot.py :/boot.py
python -m mpremote connect COM!PORT! cp !FW_DIR!\app_config.py :/app_config.py
python -m mpremote connect COM!PORT! cp !FW_DIR!\relay_hw.py :/relay_hw.py
python -m mpremote connect COM!PORT! cp !FW_DIR!\ap_config.py :/ap_config.py
python -m mpremote connect COM!PORT! cp !FW_DIR!\config.py :/config.py
python -m mpremote connect COM!PORT! cp !FW_DIR!\main.py :/main.py
python -m mpremote connect COM!PORT! mkdir umqtt 2>nul
python -m mpremote connect COM!PORT! cp !FW_DIR!\umqtt\simple.py :umqtt\simple.py

echo.
echo === [4/4] Reset ===
python -m mpremote connect COM!PORT! reset

echo.
echo === DONE ===
pause
