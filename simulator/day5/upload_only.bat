@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Day5 - 仅上传 ESP32 源码
echo ========================================
echo   Day5 仅上传 ESP32 源码  不擦不重烧
echo   注意: 执行前先关闭所有串口监控窗口
echo ========================================
echo.

set PORT=
set /p PORT=请输入 COM 口  直接回车默认 COM5:
if "!PORT!"=="" set PORT=COM5

cd /d "%~dp0"
set FW_DIR=esp32_firmware

echo.
echo === 上传固件源码 ===
python -m mpremote connect !PORT! cp !FW_DIR!\boot.py :/boot.py
python -m mpremote connect !PORT! cp !FW_DIR!\app_config.py :/app_config.py
python -m mpremote connect !PORT! cp !FW_DIR!\relay_hw.py :/relay_hw.py
python -m mpremote connect !PORT! cp !FW_DIR!\ap_config.py :/ap_config.py
python -m mpremote connect !PORT! cp !FW_DIR!\config.py :/config.py
python -m mpremote connect !PORT! cp !FW_DIR!\main.py :/main.py
python -m mpremote connect !PORT! mkdir umqtt 2>nul
python -m mpremote connect !PORT! cp !FW_DIR!\umqtt\simple.py :umqtt\simple.py

echo.
echo === 重启板子 ===
python -m mpremote connect !PORT! reset

echo.
echo --- 完成, 板子已重启 ---
pause
