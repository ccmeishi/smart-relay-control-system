@echo off
chcp 65001 >nul 2>&1
title Day5 - ESP32 Firmware Upload & Serial Monitor
echo ========================================
echo   Day5 ESP32 固件烧录 + 上传 + 监控
echo   流程: 擦除 - 烧 MicroPython - 上传源码 - 监控串口
echo ========================================
echo.
cd /d "%~dp0"
set FW_DIR=esp32_firmware

set /p PORT=请输入 COM 口 (如 COM5, 直接回车默认 COM5):
if "%PORT%"=="" set PORT=COM5

echo.
echo --- [1/4] 擦除旧固件 ---
python -m esptool --port %PORT% erase_flash
if errorlevel 1 (
    echo [错误] 擦除失败
    pause & exit /b 1
)

echo.
echo --- [2/4] 烧录 MicroPython 解释器 ---
python -m esptool --port %PORT% --chip esp32c3 flash_mode dio --flash_freq 40m flash_id %FW_DIR%\_firmware\ESP32_GENERIC_C3-v1.29.0.bin
if errorlevel 1 (
    echo [错误] 烧录 MicroPython 失败
    pause & exit /b 1
)

echo.
echo --- [3/4] 上传固件源码 ---
python -m mpremote connect %PORT% cp %FW_DIR%\boot.py :/boot.py
python -m mpremote connect %PORT% cp %FW_DIR%\app_config.py :/app_config.py
python -m mpremote connect %PORT% cp %FW_DIR%\relay_hw.py :/relay_hw.py
python -m mpremote connect %PORT% cp %FW_DIR%\ap_config.py :/ap_config.py
python -m mpremote connect %PORT% cp %FW_DIR%\config.py :/config.py
python -m mpremote connect %PORT% cp %FW_DIR%\main.py :/main.py
python -m mpremote connect %PORT% mkdir umqtt 2>nul
python -m mpremote connect %PORT% cp %FW_DIR%\umqtt\simple.py :umqtt\simple.py
echo   源码上传完成

echo.
echo --- [4/4] 串口监控 (Ctrl+C 退出) ---
echo   预期看到: WiFi OK, MQTT 已连接
echo.
python -c "import serial,time; s=serial.Serial('%PORT%',115200,timeout=1); time.sleep(2); print(s.read(s.in_waiting or 4096).decode('utf-8','replace')); s.close()"
echo.
echo --- 如需持续监控, 双击 start_serial.bat ---
pause
