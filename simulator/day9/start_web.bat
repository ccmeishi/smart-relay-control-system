@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Day9 Web Management GUI

echo ========================================
echo   Day9 Web Management GUI
echo ========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.8+ and add to PATH.
    pause
    exit /b 1
)

python -c "import flask" 2>nul
if errorlevel 1 (
    echo [ERROR] Missing dependencies. Run:
    echo         pip install flask
    pause
    exit /b 1
)

cd /d "%~dp0"

:: Init DB
python db.py

echo.
echo Starting Web GUI on http://127.0.0.1:8081
echo Press Ctrl+C to stop.
echo.

python web\app.py

pause
