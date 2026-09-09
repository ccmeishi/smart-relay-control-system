@echo off
setlocal enabledelayedexpansion
title Day8 Upload (Multi-Device Architecture)
echo ========================================
echo   Day8 多设备固件增量上传
echo   Upload ALL source from simulator\esp32
echo   NOTE: close all serial monitor windows first
echo ========================================
echo.

set PORT=
set /p PORT=COM number (default 5):
if "!PORT!"=="" set PORT=5

cd /d "%~dp0"
set "SRC=%~dp0..\esp32"

echo.
echo === Uploading Day8 files ===
echo   boot.py, relay_hw.py, app_config.py, ap_config.py
echo   modbus_gw.py, main.py, umqtt/simple.py

python -m mpremote connect COM!PORT! rm boot.py 2>nul
python -m mpremote connect COM!PORT! rm relay_hw.py 2>nul
python -m mpremote connect COM!PORT! rm app_config.py 2>nul
python -m mpremote connect COM!PORT! rm ap_config.py 2>nul
python -m mpremote connect COM!PORT! rm modbus_gw.py 2>nul
python -m mpremote connect COM!PORT! rm main.py 2>nul
python -m mpremote connect COM!PORT! rm config.json 2>nul

python -m mpremote connect COM!PORT! cp "!SRC!\boot.py" :/boot.py
python -m mpremote connect COM!PORT! cp "!SRC!\relay_hw.py" :/relay_hw.py
python -m mpremote connect COM!PORT! cp "!SRC!\app_config.py" :/app_config.py
python -m mpremote connect COM!PORT! cp "!SRC!\ap_config.py" :/ap_config.py
python -m mpremote connect COM!PORT! cp "!SRC!\modbus_gw.py" :/modbus_gw.py
python -m mpremote connect COM!PORT! cp "!SRC!\main.py" :/main.py
python -m mpremote connect COM!PORT! mkdir umqtt 2>nul
python -m mpremote connect COM!PORT! cp "!SRC!\umqtt\simple.py" :umqtt\simple.py

echo.
echo === Reset board ===
python -m mpremote connect COM!PORT! reset

echo.
echo === DONE ===
echo   Next: 板子会进配网模式 (config.json 已删)
echo   手机连 RELAY-SETUP-xxxx -> http://192.168.4.1
echo   填 WiFi + 共享 MQTT + relay-cc + sensor-cc + Modbus JSON
echo.
pause
