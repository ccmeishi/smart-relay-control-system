@echo off
setlocal enabledelayedexpansion
title Day5 Upload ESP32 Source
echo ========================================
echo   Day5 upload ESP32 source only
echo   NOTE: close all serial monitor windows first
echo ========================================
echo.

set PORT=
set /p PORT=COM number (default 5):
if "!PORT!"=="" set PORT=5

cd /d "%~dp0"
set FW_DIR=esp32_firmware

echo.
echo === Uploading source ===
python -m mpremote connect COM!PORT! cp !FW_DIR!\boot.py :/boot.py
python -m mpremote connect COM!PORT! cp !FW_DIR!\app_config.py :/app_config.py
python -m mpremote connect COM!PORT! cp !FW_DIR!\relay_hw.py :/relay_hw.py
python -m mpremote connect COM!PORT! cp !FW_DIR!\ap_config.py :/ap_config.py
python -m mpremote connect COM!PORT! cp !FW_DIR!\config.py :/config.py
python -m mpremote connect COM!PORT! cp !FW_DIR!\main.py :/main.py
python -m mpremote connect COM!PORT! mkdir umqtt 2>nul
python -m mpremote connect COM!PORT! cp !FW_DIR!\umqtt\simple.py :umqtt\simple.py

echo.
echo === Reset board ===
python -m mpremote connect COM!PORT! reset

echo.
echo === DONE ===
pause
