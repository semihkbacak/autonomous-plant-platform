@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Autonomous Plant P04 - FULL SOURCE - Windows first run
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
echo ================================================================
echo    AUTONOMOUS PLANT PLATFORM - P04 - COMPLETE SOURCE
echo    HES / GES / RES - SYNTHETIC SIMULATION ONLY
echo ================================================================
echo    Project directory: %CD%
echo    This package is P04 FULL SOURCE. No old-folder patch required.
echo    Close previous simulators using 127.0.0.1:8000 before starting.
echo.
if not exist "APP_VERSION_P03.txt" goto INCOMPLETE
if not exist "APP_VERSION_P04.txt" goto INCOMPLETE
if not exist "app\main.py" goto INCOMPLETE
if not exist "advanced_v2\api.py" goto INCOMPLETE
if not exist "stage1\controller.py" goto INCOMPLETE
if not exist "desktop\full_simulator_launcher.py" goto INCOMPLETE
if not exist "windows\windows_start.py" goto INCOMPLETE
if not exist "tests\test_windows_utf8_portability_p02.py" goto INCOMPLETE
if not exist "tests\test_windows_p03_package_entrypoints.py" goto INCOMPLETE
if not exist "requirements-windows.txt" goto INCOMPLETE
call "tools\windows_prepare_env.cmd"
if errorlevel 1 goto FAILED
call "10_WINDOWS_ASAMA2_5_TEST.cmd" --no-pause
if errorlevel 1 goto FAILED
echo.
echo [P04] FULL TESTS PASS. Starting the LOCAL synthetic simulator...
call "11_WINDOWS_ASAMA2_5_AC.cmd"
if errorlevel 1 goto FAILED
echo [P04] Local simulation window closed. No EXE or field-acceptance claim.
pause
exit /b 0
:INCOMPLETE
echo.
echo [P04] ERROR: Missing project files or running from ZIP preview.
echo Right-click P04 FULL ZIP - Extract All to a NEW EMPTY folder.
echo Run START_HERE_WINDOWS.cmd from that folder, NOT an older P01/P02/P03 folder.
echo Required folders: app, advanced_v2, stage1, desktop, windows, tests, tools.
pause
exit /b 2
:FAILED
echo.
echo [P04] Failed setup, validation or launcher. Stop: do not publish.
echo Use 10_WINDOWS_ASAMA2_5_TEST.cmd for test-only acceptance after setup.
pause
exit /b 1
