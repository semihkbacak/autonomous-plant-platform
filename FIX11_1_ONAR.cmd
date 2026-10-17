@echo off
setlocal
cd /d "%~dp0"
echo FIX11.1 - Windows path consistency repair (no reinstall)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0FIX11_1_ONAR.ps1"
set "RC=%ERRORLEVEL%"
if "%RC%"=="0" (
 echo Repair PASSED. Now launch 06_WINDOWS_TAM_EXE_DERLE.cmd
) else (
 echo Repair FAILED. Read the messages above.
)
echo Press any key to close.
pause >nul
exit /b %RC%
