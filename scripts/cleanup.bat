@echo off
chcp 65001 >nul

:: MediaFlow Cleanup Script for Windows
:: Stops services, deletes database, and clears logs
:: Usage: cleanup.bat [-f] [-k]
:: -f: force cleanup without confirmation
:: -k: keep log files

setlocal enabledelayedexpansion

for /f %%a in ('echo prompt $E^| cmd') do set "ESC=%%a"
set "RED=!ESC![0;31m"
set "GREEN=!ESC![0;32m"
set "YELLOW=!ESC![1;33m"
set "NC=!ESC![0m"

set "FORCE=false"
set "KEEP_LOGS=false"

:parse_args
if "%~1"=="" goto :args_parsed
if /i "%~1"=="-f" (set "FORCE=true"
) else if /i "%~1"=="--force" (set "FORCE=true"
) else if /i "%~1"=="-k" (set "KEEP_LOGS=true"
) else if /i "%~1"=="--keep-logs" (set "KEEP_LOGS=true"
) else (
    echo Unknown option: %~1
    echo Usage: %~nx0 [-f^|--force] [-k^|--keep-logs]
    exit /b 1
)
shift
goto :parse_args

:args_parsed

if /i not "%FORCE%"=="true" (
    echo This script will:
    echo - Stop all MediaFlow services
    echo - Delete the database file ^(backend\mediaflow.db^)
    if /i not "%KEEP_LOGS%"=="true" (
        echo - Delete all log files ^(logs\*.log and logs\*.pid^)
    ) else (
        echo - Keep log files ^(as requested with -k option^)
    )
    echo.
    set /p CONFIRM="Are you sure? ^(y/N^): "
    if /i not "!CONFIRM!"=="y" (
        echo Cleanup cancelled.
        exit /b 0
    )
)

echo [i] Starting MediaFlow cleanup...

:: Step 1: Stop all services
echo [i] Stopping all services...
for %%f in (logs\*.pid) do (
    set /p PID=<"%%f"
    if defined PID (
        taskkill /pid !PID! /f >nul 2>&1
        del "%%f" >nul 2>&1
    )
)
echo %GREEN%[OK]%NC% Services stopped

:: Step 2: Delete database file
if exist "backend\mediaflow.db" (
    del backend\mediaflow.db
    echo %GREEN%[OK]%NC% Database file deleted
) else (
    echo %YELLOW%[!]%NC% Database file not found
)

:: Step 3: Clean up log files
if /i not "%KEEP_LOGS%"=="true" (
    if exist "logs\*.log" (
        del logs\*.log
        echo %GREEN%[OK]%NC% Log files deleted
    )
    if exist "logs\*.pid" (
        del logs\*.pid
    )
) else (
    echo [i] Keeping log files as requested
)

echo %GREEN%[OK]%NC% Cleanup completed. Run "python scripts\services.py start" to start fresh.

endlocal
exit /b 0
