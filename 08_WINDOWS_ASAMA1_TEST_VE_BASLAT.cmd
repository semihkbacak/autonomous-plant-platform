@echo off
setlocal
cd /d "%~dp0"
if not exist "app\main.py" goto BAD
if not exist "stage1\controller.py" goto BAD
if not exist ".venv\Scripts\python.exe" (
  echo [STAGE1] Missing Python environment. Run 01_WINDOWS_KUR_TEST_VE_BASLAT.cmd first.
  pause
  exit /b 2
)
echo [STAGE1] Running 3-plant UTC synchronization/recovery tests...
".venv\Scripts\python.exe" -m pytest -q --assert=plain tests\test_stage1_three_plant_sync.py
if errorlevel 1 (
  echo [STAGE1] FAILED. No application started. Send this output.
  pause
  exit /b 1
)
echo [STAGE1] Tests passed. Opening local synthetic desktop...
call "05_WINDOWS_MASAUSTU_SIMULATORU.cmd"
exit /b %ERRORLEVEL%
:BAD
echo ERROR: ZIP not fully extracted or Stage1 files missing.
pause
exit /b 2
