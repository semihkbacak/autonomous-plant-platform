@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo ERROR: Run 01_WINDOWS_KUR_TEST_VE_BASLAT.cmd first.
  pause
  exit /b 2
)
echo Creating/validating OFFLINE SYNTHETIC GES sample history...
echo This is not measured plant data. Existing historian will not be overwritten.
".venv\Scripts\python.exe" -m tools.prepare_ges_history
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo ERROR: GES history preparation failed; send console output.
if "%RC%"=="0" echo DONE. Restart the local simulator, then refresh GES analytics.
pause
exit /b %RC%
