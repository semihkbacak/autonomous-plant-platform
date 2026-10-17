@echo off
setlocal
cd /d "%~dp0"
set "LOG=%~dp0WINDOWS_EXE_DERLEME_RAPORU.txt"
echo ============================================================
echo   Autonomous Plant v2.0 - Windows EXE Build + Log
 echo ============================================================
if not exist "desktop\build_full_windows_v20.ps1" goto BAD
if not exist "app\main.py" goto BAD
if not exist ".venv\Scripts\python.exe" (
 echo ERROR: First run 01_WINDOWS_KUR_TEST_VE_BASLAT.cmd from the extracted folder.
 goto FAILED
)
echo The process can take several minutes. Do not close this window.
echo Build output/log: "%LOG%"
powershell -NoProfile -ExecutionPolicy Bypass -File "desktop\build_full_windows_v20.ps1" -LogPath "%LOG%"
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
  if exist "dist\AutonomousPlantSimulatorV20_FIX11\AutonomousPlantSimulatorV20_FIX11.exe" (
    echo SUCCESS: dist\AutonomousPlantSimulatorV20_FIX11\AutonomousPlantSimulatorV20_FIX11.exe
    echo The full dist folder is required. A Desktop shortcut was attempted.
  ) else (
    echo ERROR: EXE missing despite exit code 0. Check the log.
    set "RC=1"
  )
) else (
  echo BUILD FAILED with exit code %RC%.
  echo Send the log file: "%LOG%"
)
echo.
echo Press any key after reading the result. The window will stay open.
pause >nul
exit /b %RC%
:BAD
echo ERROR: Extract the entire ZIP to a folder first.
:FAILED
echo Log would be: "%LOG%"
pause
exit /b 2
