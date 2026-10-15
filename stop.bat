@echo off
chcp 65001 >nul
cd /D "%~dp0"
python scripts\services.py stop
pause
