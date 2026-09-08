@echo off
chcp 65001 >nul
title 物联网网关 - 一键启动

echo ========================================
echo   ESP32 Modbus网关 + Bridge 启动脚本
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3
    pause
    exit /b 1
)

cd /d "%~dp0"

echo [1/2] 启动 Modbus TCP 从站模拟器 (端口 5502, unit_id=7)...
start "Modbus模拟器" cmd /k "python -u modbus_slave_sim.py 5502 7"

timeout /t 2 /nobreak >nul

echo [2/2] 启动 Python Bridge (订阅网关, 转发虚拟产品)...
start "Bridge" cmd /k "python -u gateway_bridge.py"

echo.
echo ========================================
echo   启动完成！
echo ========================================
echo.
echo   Modbus模拟器: 0.0.0.0:5502 (unit_id=7)
echo   Bridge:       订阅 relay-cc/relaycc/# 转发到 6 个虚拟产品
echo.
echo   常用命令:
echo     python set_modbus.py 25 60 1 50   (改温度/湿度/人体/烟雾)
echo     python set_modbus.py --human 0    (只改人体为无人)
echo.
echo   关闭: 直接关闭弹出的两个 cmd 窗口
echo.
pause
