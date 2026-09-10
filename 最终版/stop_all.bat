@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Smart Relay Control System - Stop All
cd /d "%~dp0"

echo ============================================================
echo   Stopping Smart Relay Control System services...
echo ============================================================
echo.

REM ---- Stop backend on port 8083 ----
echo [Stop] Checking port 8083 - backend...
set FOUND_8083=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8083 " ^| findstr "LISTENING"') do (
    echo        Found backend PID %%a - killing...
    taskkill /pid %%a /f >nul 2>&1
    set FOUND_8083=1
)
if "!FOUND_8083!"=="0" echo        Port 8083 is not in use.

REM ---- Stop frontend dev server on port 5173 ----
echo [Stop] Checking port 5173 - frontend dev server...
set FOUND_5173=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    echo        Found frontend PID %%a - killing...
    taskkill /pid %%a /f >nul 2>&1
    set FOUND_5173=1
)
if "!FOUND_5173!"=="0" echo        Port 5173 is not in use.

REM ---- Kill by window title ----
echo [Stop] Closing service windows...
taskkill /fi "WINDOWTITLE eq IoT-Backend*" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq IoT-Frontend-Dev*" /f >nul 2>&1

echo.
echo ============================================================
echo   All services stopped.
echo ============================================================
echo.
pause
