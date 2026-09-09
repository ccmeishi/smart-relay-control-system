@echo off
setlocal enabledelayedexpansion
title ESP32 Serial Monitor
echo ========================================
echo   ESP32 ������־���
echo   ������ 115200  Ctrl+C �˳�
echo ========================================
echo.

set PORT=
set /p PORT=������ COM ���  ֱ�ӻس��Զ����:
if "!PORT!"=="" (
    echo.
    echo �����Զ�̽�� ESP32 COM ��...
    for /f "usebackq delims=" %%N in (`python "%~dp0detect_com.py"`) do set PORT=%%N
    if "!PORT!"=="" (
        echo [����] δ��⵽ COM ��
        echo   ��ȷ�� ESP32 ������ USB ��
        echo   ���ֶ����� COM ����� 5
        pause & exit /b 1
    )
    echo ��⵽ COM!PORT!
)

echo.
echo === ��ʼ��� COM!PORT! ===
python -m serial.tools.miniterm COM!PORT! 115200 --rts 0 --dtr 0
echo.
echo === ��ؽ��� ===
pause
