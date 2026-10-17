@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Autonomous Plant P04 - ALL tests and UTC browser/API acceptance
if not exist "APP_VERSION_P04.txt" goto WRONG
call "tools\windows_prepare_env.cmd"
if errorlevel 1 goto FAIL
call "10_WINDOWS_ASAMA2_5_TEST.cmd" --no-pause
if errorlevel 1 goto FAIL
echo.
echo [P04] ALL CLI regression tests passed. GUI click acceptance is separate.
pause
exit /b 0
:WRONG
echo [P04] Extract P04 FULL ZIP into a new empty folder.
pause
exit /b 2
:FAIL
echo [P04] Tests failed. See the preceding output.
pause
exit /b 1
