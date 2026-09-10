@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
title Smart Relay Control System - Stop All
cd /d "%~dp0"

echo ============================================================
echo   Stopping Smart Relay Control System services...
echo ============================================================
echo.

REM ---- 1. Kill backend process tree by port 8083 ----
echo [Stop] Step 1/3 - Backend on port 8083 (kill tree)...
set FOUND_8083=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8083 " ^| findstr "LISTENING"') do (
    echo        Found PID %%a - killing process tree...
    taskkill /pid %%a /f /t >nul 2>&1
    set FOUND_8083=1
)
if "!FOUND_8083!"=="0" echo        Port 8083 is free.

REM ---- 2. Kill frontend dev server process tree by port 5173 ----
echo [Stop] Step 2/3 - Frontend dev server on port 5173 (kill tree)...
set FOUND_5173=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":5173 " ^| findstr "LISTENING"') do (
    echo        Found PID %%a - killing process tree...
    taskkill /pid %%a /f /t >nul 2>&1
    set FOUND_5173=1
)
if "!FOUND_5173!"=="0" echo        Port 5173 is free.

REM ---- 3. Kill orphan bridge python processes by command line ----
echo [Stop] Step 3/3 - Killing orphan bridge python processes...
set BRIDGE_KILLED=0
for /f "tokens=2 delims=," %%a in ('wmic process where "name='python.exe' and (commandline like '%%fake_bridge%%' or commandline like '%%gateway_bridge%%')" get processid /format:csv ^| findstr /r "[0-9]"') do (
    echo        Found bridge PID %%a - killing...
    taskkill /pid %%a /f >nul 2>&1
    set BRIDGE_KILLED=1
)
if "!BRIDGE_KILLED!"=="0" echo        No orphan bridge processes found.

REM ---- 4. Kill by window title as fallback ----
echo [Stop] Fallback - closing service windows by title...
taskkill /fi "WINDOWTITLE eq IoT-Backend*" /f /t >nul 2>&1
taskkill /fi "WINDOWTITLE eq IoT-Frontend-Dev*" /f /t >nul 2>&1

REM ---- 5. Wait and verify ports are released ----
timeout /t 3 /nobreak >nul

echo.
echo [Verify] Checking ports after cleanup...
set VERIFY_OK=1
netstat -ano | findstr ":8083 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [WARN] Port 8083 is still in use after cleanup.
    echo        Try: taskkill /pid ^<pid^> /f /t
    set VERIFY_OK=0
) else (
    echo        Port 8083 is free.
)

netstat -ano | findstr ":5173 " | findstr "LISTENING" >nul 2>&1
if not errorlevel 1 (
    echo [WARN] Port 5173 is still in use after cleanup.
    echo        Try: taskkill /pid ^<pid^> /f /t
    set VERIFY_OK=0
) else (
    echo        Port 5173 is free.
)

echo.
if "!VERIFY_OK!"=="1" (
    echo ============================================================
    echo   All services stopped cleanly.
    echo ============================================================
) else (
    echo ============================================================
    echo   Some ports still occupied - see warnings above.
    echo ============================================================
)
echo.
pause
