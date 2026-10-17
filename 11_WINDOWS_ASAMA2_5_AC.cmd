@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Autonomous Plant P04 - Windows Desktop Simulator
call "tools\windows_prepare_env.cmd"
if errorlevel 1 goto BOOTFAIL
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "APP_OPERATION_MODE=SIMULATION"
echo [P04] Starting LOCAL SYNTHETIC simulator (not real OT/PLC control)...
".venv\Scripts\python.exe" -m desktop.full_simulator_launcher
if errorlevel 1 goto FAILED
exit /b 0
:BOOTFAIL
echo [P04] Environment or project incomplete. See above.
pause
exit /b 2
:FAILED
echo [P04] Desktop launcher failed. Review local logs.
pause
exit /b 1
