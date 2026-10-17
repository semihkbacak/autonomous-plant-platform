@echo off
setlocal
cd /d "%~dp0"
if not exist "ASAMA1_DOSYA_MANIFEST.json" goto BAD
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" "scripts\verify_stage1_delivery.py"
) else (
  py -3.13 "scripts\verify_stage1_delivery.py"
)
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (echo [STAGE1] FILE INTEGRITY PASSED) else (echo [STAGE1] FILE INTEGRITY FAILED - send output)
pause
exit /b %RC%
:BAD
echo ERROR: Extract the complete Stage 1 ZIP first.
pause
exit /b 2
