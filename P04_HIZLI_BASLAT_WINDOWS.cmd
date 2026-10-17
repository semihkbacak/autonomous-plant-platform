@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Autonomous Plant P04 - LOCAL ONLY synthetic simulator
if not exist "APP_VERSION_P04.txt" goto WRONG
call "tools\windows_prepare_env.cmd"
if errorlevel 1 goto FAIL
set "APP_OPERATION_MODE=SIMULATION"
set "PYTHONUTF8=1"
echo [P04] Starting local HES/GES/RES GUI. Use UTC synchronized button.
echo [P04] If port 8000 is occupied, close the old simulator; do NOT kill unknown processes.
".venv\Scripts\python.exe" -m desktop.full_simulator_launcher
if errorlevel 1 goto FAIL
exit /b 0
:WRONG
echo [P04] This launcher is NOT in the complete extracted P04 source folder.
pause
exit /b 2
:FAIL
echo [P04] Start failed. Check messages above. Keep Windows security enabled.
pause
exit /b 1
