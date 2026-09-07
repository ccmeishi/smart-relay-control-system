@echo off
setlocal enabledelayedexpansion
title Day5 - ESP32 全流程烧录
echo ========================================
echo   Day5 ESP32 擦除 + 烧录 + 上传源码
echo   注意: 执行前先关闭所有串口监控窗口
echo ========================================
echo.

set PORT=
set /p PORT=请输入 COM 口  直接回车默认 COM5:
if "!PORT!"=="" set PORT=COM5

cd /d "%~dp0"
set FW_DIR=esp32_firmware

where python >nul 2>&1
if !errorlevel! neq 0 ( echo [错误] 未安装 Python & pause & exit /b 1 )
where esptool >nul 2>&1
if !errorlevel! neq 0 ( pip install esptool mpremote pyserial )

echo.
echo === [1/4] 擦除旧固件 ===
python -m esptool --port !PORT! erase_flash
if !errorlevel! neq 0 (
    echo [错误] 擦除失败, 检查 COM 口和板子
    pause & exit /b 1
)

echo.
echo === [2/4] 烧录 MicroPython v1.29.0 ===
python -m esptool --port !PORT! --chip esp32c3 flash_mode dio --flash_freq 40m flash_id !FW_DIR!\_firmware\ESP32_GENERIC_C3-v1.29.0.bin
if !errorlevel! neq 0 (
    echo [错误] 烧录失败
    pause & exit /b 1
)

echo.
echo === [3/4] 上传固件源码 ===
python -m mpremote connect !PORT! cp !FW_DIR!\boot.py :/boot.py
python -m mpremote connect !PORT! cp !FW_DIR!\app_config.py :/app_config.py
python -m mpremote connect !PORT! cp !FW_DIR!\relay_hw.py :/relay_hw.py
python -m mpremote connect !PORT! cp !FW_DIR!\ap_config.py :/ap_config.py
python -m mpremote connect !PORT! cp !FW_DIR!\config.py :/config.py
python -m mpremote connect !PORT! cp !FW_DIR!\main.py :/main.py
python -m mpremote connect !PORT! mkdir umqtt 2>nul
python -m mpremote connect !PORT! cp !FW_DIR!\umqtt\simple.py :umqtt\simple.py
echo   源码上传完成

echo.
echo === [4/4] 重启板子 ===
python -m mpremote connect !PORT! reset
echo.
echo --- 完成, 板子已重启 ---
pause
