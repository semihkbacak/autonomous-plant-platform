@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Autonomous Plant P04 - Windows UTF-8 Regression
call "tools\windows_prepare_env.cmd"
if errorlevel 1 goto BOOTFAIL
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
set "PYTHONDONTWRITEBYTECODE=1"
set "TEST_TEMP=%CD%\.windows_test_tmp\p03_utf8"
if not exist "%TEST_TEMP%" mkdir "%TEST_TEMP%"
echo [P04] Verify Windows cp1254 UTF-8 decoding and full-package preflight...
".venv\Scripts\python.exe" -m pytest -q --assert=plain --tb=short --basetemp="%TEST_TEMP%" tests\test_windows_utf8_portability_p02.py tests\test_windows_p03_package_entrypoints.py tests\test_stage1_three_plant_sync.py::test_builder_bundles_stage1_and_entrypoints tests\test_stages_2_to_5_advanced.py::test_python_windows_builder_and_gui_include_new_modules
if errorlevel 1 goto FAILED
echo [P04] Encoding test passed. FULL regression: 10_WINDOWS_ASAMA2_5_TEST.cmd
pause
exit /b 0
:BOOTFAIL
echo [P04] Environment or project incomplete. See above.
pause
exit /b 2
:FAILED
echo [P04] Encoding regression FAILED. Do not publish.
pause
exit /b 1
