@echo off
setlocal
cd /d "%~dp0"
if not exist "windows\windows_start.py" goto NEED_EXTRACT
if not exist "app\main.py" goto NEED_EXTRACT
if not exist "requirements.txt" goto NEED_EXTRACT
py -3.13 "windows\windows_start.py" --build-exe
if errorlevel 1 (
 echo.
 echo Setup failed. Check messages. Do not disable Windows security.
 pause
 exit /b 1
)
echo Completed.
pause
exit /b 0

:NEED_EXTRACT
echo.
echo ERROR: You launched from inside ZIP or an incomplete project folder.
echo In File Explorer RIGHT CLICK ZIP ^> Extract All ^> choose C:\AutonomousPlantV20
echo Open the EXTRACTED project directory, then run this CMD again.
echo Required: windows\windows_start.py, app\main.py, requirements.txt
echo No files were changed.
pause
exit /b 2
