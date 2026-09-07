@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Day7 - 上传 Modbus 网关增量文件
echo ========================================
echo   Day7 增量: 上传 Modbus 网关相关文件
echo   新增: modbus_gw.py
echo   修改: app_config.py, ap_config.py, main.py
echo   注意: 执行前关闭所有串口监控窗口
echo ========================================
echo.

set PORT=
set /p PORT=请输入 COM 口 (直接回车默认 COM5):
if "!PORT!"=="" set PORT=COM5

cd /d "%~dp0"

echo.
echo === 上传 Day7 新增/修改文件 ===
python -m mpremote connect !PORT! cp esp32_firmware\modbus_gw.py :/modbus_gw.py
python -m mpremote connect !PORT! cp esp32_firmware\app_config.py :/app_config.py
python -m mpremote connect !PORT! cp esp32_firmware\ap_config.py :/ap_config.py
python -m mpremote connect !PORT! cp esp32_firmware\main.py :/main.py

echo.
echo === 重启板子 ===
python -m mpremote connect !PORT! reset

echo.
echo --- 完成, 板子已重启 ---
echo --- 串口应看到: Modbus 网关已启动, 采集点: N ---
pause