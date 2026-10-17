@echo off
setlocal
cd /d "%~dp0"
if not exist "windows\windows_start.py" goto NEED_EXTRACT
if not exist "app\main.py" goto NEED_EXTRACT
if not exist "requirements.txt" goto NEED_EXTRACT
if not exist ".venv\Scripts\python.exe" (
 echo Install first: 01_WINDOWS_KUR_TEST_VE_BASLAT.cmd
 pause
 exit /b 1
)
".venv\Scripts\python.exe" -m desktop.full_simulator_launcher
if errorlevel 1 pause
exit /b %ERRORLEVEL%

:NEED_EXTRACT
echo.
echo ERROR: You launched from inside ZIP or an incomplete project folder.
echo In File Explorer RIGHT CLICK ZIP ^> Extract All ^> choose C:\AutonomousPlantV20
echo Open the EXTRACTED project directory, then run this CMD again.
echo Required: windows\windows_start.py, app\main.py, requirements.txt
echo No files were changed.
pause
exit /b 2
