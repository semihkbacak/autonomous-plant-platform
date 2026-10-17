@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Run 01_WINDOWS_KUR_TEST_VE_BASLAT.cmd first.
  exit /b 1
)
".venv\Scripts\python.exe" tools\audit_repair_backup.py windows\windows_start.py pytest.ini stage1\controller.py stage1\engine.py stage1\store.py
if errorlevel 1 exit /b 1
echo Backups placed OUTSIDE this project: ..\AutonomousPlant_RepairBackups
exit /b 0
