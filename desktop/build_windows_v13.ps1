# Execute on Windows 10/11, in the repository root. This is a viewer build,
# NOT a physical plant control product. Clean-room Windows QA is required.
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $repo
if (-not (Test-Path 'desktop\plant_viewer.py')) { throw 'v1.2 desktop\plant_viewer.py missing' }
py -3 -m venv .viewer-build-env
$python = Join-Path $repo '.viewer-build-env\Scripts\python.exe'
& $python -m pip install --upgrade pip
& $python -m pip install 'pyinstaller>=6,<7'
& $python -m PyInstaller --clean --noconfirm --onefile --windowed --name AutonomousPlantViewer --distpath (Join-Path $repo 'desktop\dist') 'desktop\plant_viewer.py'
& $python -m desktop.windows_release_preflight --exe 'desktop\dist\AutonomousPlantViewer.exe' --report 'desktop\dist\viewer-preflight.json'
Write-Host 'EXE created but UNSIGNED/NOT APPROVED. Never use as an OT command gateway.'
