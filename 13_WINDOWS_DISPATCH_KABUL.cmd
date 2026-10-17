@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Autonomous Plant P04 - Synthetic UTC Dispatch QA
call "tools\windows_prepare_env.cmd"
if errorlevel 1 goto BOOTFAIL
set "APP_OPERATION_MODE=SIMULATION"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
set "TEMP=%CD%\.windows_test_tmp"
set "TMP=%TEMP%"
if not exist "%TEMP%" mkdir "%TEMP%"
echo [P04] Synthetic dispatch, UTC recovery, Windows/Linux discovery regression...
".venv\Scripts\python.exe" -m pytest -q --assert=plain --tb=short --basetemp="%TEMP%\p03_dispatch" tests\test_stage1_three_plant_sync.py tests\test_stage1_dispatch_schedule_p01.py tests\test_stages_2_to_5_advanced.py tests\test_windows_utf8_portability_p02.py tests\test_windows_p03_package_entrypoints.py
if errorlevel 1 goto FAILED
echo [P04] Targeted regressions passed. FULL suite remains mandatory: 10_WINDOWS_ASAMA2_5_TEST.cmd
pause
exit /b 0
:BOOTFAIL
echo [P04] Missing/incomplete installation. See diagnostics above.
pause
exit /b 2
:FAILED
echo [P04] Targeted regression FAILED. DO NOT PUBLISH.
pause
exit /b 1
