@echo off
setlocal
cd /d "%~dp0"
py -3.13 "windows\windows_start.py"
if errorlevel 1 (
  echo.
  echo Installation or test failed. See the error above.
  echo Verify Windows Python 3.13 and internet access.
  pause
  exit /b 1
)
echo.
echo Finished. You can close this setup window.
pause
