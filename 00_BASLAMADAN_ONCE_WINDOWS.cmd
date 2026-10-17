@echo off
setlocal EnableExtensions
cd /d "%~dp0"
if not exist "APP_VERSION_P03.txt" goto BAD
call "START_HERE_WINDOWS.cmd"
exit /b %ERRORLEVEL%
:BAD
echo ERROR: This is not the extracted P03 COMPLETE project.
echo Extract the NEW FULL ZIP to a fresh folder, then run START_HERE_WINDOWS.cmd
pause
exit /b 2
