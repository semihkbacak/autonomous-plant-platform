@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Autonomous Plant P03 - Windows launcher
if not exist "APP_VERSION_P03.txt" goto NEED_EXTRACT
if not exist "app\\main.py" goto NEED_EXTRACT
if not exist "windows\\windows_start.py" goto NEED_EXTRACT
if not exist "requirements-windows.txt" goto NEED_EXTRACT
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
py -3.13 "windows\\windows_start.py" --skip-tests
if errorlevel 1 goto FAILED
echo [P03] Operation completed.
pause
exit /b 0
:FAILED
echo [P03] FAILED; see the error above. Do not disable Windows security.
pause
exit /b 1
:NEED_EXTRACT
echo [P03] WRONG DIRECTORY. Extract FULL P03 ZIP to a NEW EMPTY folder.
echo Run this .cmd from same folder as APP_VERSION_P03.txt, app, tests, stage1, desktop.
pause
exit /b 2
