@echo off
setlocal EnableExtensions
cd /d "%~dp0.."
if not exist "APP_VERSION_P03.txt" goto INCOMPLETE
if not exist "APP_VERSION_P04.txt" goto INCOMPLETE
if not exist "app\main.py" goto INCOMPLETE
if not exist "advanced_v2\api.py" goto INCOMPLETE
if not exist "stage1\controller.py" goto INCOMPLETE
if not exist "tests\test_stage1_three_plant_sync.py" goto INCOMPLETE
if not exist "windows\windows_start.py" goto INCOMPLETE
if not exist "requirements-windows.txt" goto INCOMPLETE
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
if not exist ".venv\Scripts\python.exe" goto SETUP
echo [P04] Checking existing Windows virtual environment...
".venv\Scripts\python.exe" -c "import sys,pytest,pvlib,fastapi,sklearn; assert sys.platform=='win32' and sys.version_info[:2]==(3,13) and sklearn.__version__=='1.9.1'" >nul 2>&1
if not errorlevel 1 (
 echo [P04] Existing Python environment accepted.
 exit /b 0
)
echo [P04] Existing environment needs repair or has wrong dependencies.
:SETUP
where py >nul 2>&1
if errorlevel 1 (
 echo [P04] Python launcher missing. Install Python 3.13 with Windows py launcher enabled.
 exit /b 3
)
py -3.13 -c "import sys; assert sys.platform=='win32' and sys.version_info[:2]==(3,13)"
if errorlevel 1 (
 echo [P04] Windows Python 3.13 is required. Install Python 3.13, then retry.
 exit /b 3
)
echo [P04] Preparing complete Windows venv. This can install Python dependencies.
py -3.13 "windows\windows_start.py" --setup-only
if errorlevel 1 (
 echo [P04] Environment initialization FAILED. See above error; no tests were run.
 exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
 echo [P04] Setup returned without creating the venv. Stop.
 exit /b 1
)
exit /b 0
:INCOMPLETE
echo.
echo [P04] WRONG FOLDER OR INCOMPLETE PROJECT.
echo This file must be in the complete extracted P03 source project.
echo Download the P04 FULL ZIP, right-click and Extract All into a NEW folder.
echo Keep tools, windows, stage1, advanced_v2, desktop, tests, app together.
echo Current directory: %CD%
exit /b 2
