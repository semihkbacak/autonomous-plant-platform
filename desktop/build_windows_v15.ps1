# Native Windows build only. Bundles a READ-ONLY viewer, not the plant simulator/server.
$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repo
if (-not (Test-Path 'desktop\viewer_entry_v15.py')) { throw 'Missing v1.5 viewer entry' }
if (-not (Test-Path 'desktop\plant_viewer.py')) { throw 'Missing v1.2 read-only viewer' }
py -3.13 -m venv .viewer-v15-buildenv
$python = Join-Path $repo '.viewer-v15-buildenv\Scripts\python.exe'
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'pip bootstrap failed' }
& $python -m pip install 'pyinstaller==6.16.0'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller install failed' }
& $python -m desktop.viewer_entry_v15 --self-test
if ($LASTEXITCODE -ne 0) { throw 'Viewer entry self-test failed' }
& $python -m PyInstaller --clean --noconfirm --onefile --windowed --name AutonomousPlantViewer --distpath (Join-Path $repo 'desktop\dist') --paths $repo desktop\viewer_entry_v15.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller build failed' }
$exe = Join-Path $repo 'desktop\dist\AutonomousPlantViewer.exe'
if (-not (Test-Path $exe)) { throw 'EXE not found after PyInstaller' }
& $exe --self-test
if ($LASTEXITCODE -ne 0) { throw 'Built EXE smoke test failed' }
& $python -m desktop.verify_windows_v15 --exe $exe --report (Join-Path $repo 'desktop\dist\viewer_release_report.json')
if ($LASTEXITCODE -ne 0) { throw 'Windows release verification failed' }
Write-Host 'Windows preview viewer built. NOT SIGNED, NOT FIELD CONTROL VALIDATED.'
