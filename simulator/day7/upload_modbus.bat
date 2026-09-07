@echo off
setlocal enabledelayedexpansion
title Day7 Upload Modbus Gateway
echo ========================================
echo   Day7 upload Modbus gateway files
echo   Upload new: modbus_gw.py
echo   Modified: app_config.py ap_config.py main.py
echo   NOTE: close all serial monitor windows first
echo ========================================
echo.

set PORT=
set /p PORT=COM number (default 5):
if "!PORT!"=="" set PORT=5

cd /d "%~dp0"

echo.
echo === Uploading Day7 files ===
python -m mpremote connect COM!PORT! cp esp32_firmware\modbus_gw.py :/modbus_gw.py
python -m mpremote connect COM!PORT! cp esp32_firmware\app_config.py :/app_config.py
python -m mpremote connect COM!PORT! cp esp32_firmware\ap_config.py :/ap_config.py
python -m mpremote connect COM!PORT! cp esp32_firmware\main.py :/main.py

echo.
echo === Reset board ===
python -m mpremote connect COM!PORT! reset

echo.
echo === DONE ===
echo   Check serial log for: Modbus gateway started, N points
pause
