@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Autonomous Plant P04 - FULL Windows Regression
call "tools\windows_prepare_env.cmd"
if errorlevel 1 goto BOOTFAIL
set "APP_OPERATION_MODE=SIMULATION"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
set "TEST_TEMP=%CD%\.windows_test_tmp\stage2_5"
if not exist "%TEST_TEMP%" mkdir "%TEST_TEMP%"
echo [P04] Full pytest tests (not merely targeted) on Windows Python 3.13...
".venv\Scripts\python.exe" -m pytest -q --assert=plain --tb=short --basetemp="%TEST_TEMP%" tests
if errorlevel 1 goto FAILED
echo [P04] Reference and SQLite resume checks...
".venv\Scripts\python.exe" scripts\verify_stages_2_5.py
if errorlevel 1 goto FAILED
echo.
echo [P04] Windows CLI acceptance PASSED. Native GUI / EXE acceptance still required.
if /I "%~1"=="--no-pause" exit /b 0
pause
exit /b 0
:BOOTFAIL
echo [P04] Setup/preflight failed. See diagnostics above.
pause
exit /b 2
:FAILED
echo [P04] FULL REGRESSION FAILED. Do NOT publish. Send the test log.
pause
exit /b 1
