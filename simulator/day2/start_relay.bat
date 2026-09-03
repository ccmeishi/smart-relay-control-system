@echo off
title 继电器模拟器 - JetLinks直连
echo ========================================
echo   8路继电器模拟器
echo   JetLinks 直连 (方式二)
echo   产品: relay-cc  设备: relaycc
echo   Ctrl+C 退出
echo ========================================
echo.
cd /d "%~dp0"
if exist relay_data.json del relay_data.json
echo 已清理 relay_data.json 缓存
python relay_simulator_jl.py
pause
