@echo off
setlocal EnableExtensions
cd /d "%~dp0"
where git >nul 2>&1 || (echo Install Git for Windows first. & pause & exit /b 1)
where py >nul 2>&1 && (py -3 scripts\release\publish_rc1.py --publish & goto done)
python scripts\release\publish_rc1.py --publish
:done
pause
