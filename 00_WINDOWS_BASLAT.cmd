@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Autonomous Plant - P03 - Windows Menu
if not exist "APP_VERSION_P03.txt" goto BAD
if not exist "app\main.py" goto BAD
if not exist "advanced_v2\api.py" goto BAD
if not exist "stage1\controller.py" goto BAD
if not exist "windows\windows_start.py" goto BAD
:MENU
cls
echo ============================================================== 
echo   AUTONOMOUS PLANT - P03 FULL SOURCE - SYNTHETIC ONLY
echo ============================================================== 
echo   1. FIRST USE: Install, FULL test, launch
 echo   2. FULL regression tests only (auto-prepare environment)
echo   3. Open local desktop simulator (auto-prepare environment)
echo   4. P03 targeted Windows encoding tests
echo   5. Exit
echo.
choice /c 12345 /n /m "Choose 1-5: "
if errorlevel 5 goto END
if errorlevel 4 goto UTF8
if errorlevel 3 goto APP
if errorlevel 2 goto QA
if errorlevel 1 goto SETUP
goto MENU
:SETUP
call "01_WINDOWS_KUR_TEST_VE_BASLAT.cmd"
goto MENU
:QA
call "10_WINDOWS_ASAMA2_5_TEST.cmd"
goto MENU
:APP
call "11_WINDOWS_ASAMA2_5_AC.cmd"
goto MENU
:UTF8
call "14_WINDOWS_P02_KODLAMA_TEST.cmd"
goto MENU
:BAD
echo ERROR: Incomplete project / ZIP preview. Extract the FULL P03 ZIP to a NEW EMPTY folder.
echo Do not mix P01, P02 and P03 in a directory.
pause
exit /b 2
:END
exit /b 0
