# RUN ON WINDOWS ONLY with a clean Python environment and antivirus scanning.
# This builds a read-only desktop viewer; it does not bundle the simulator server.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
python -m venv .buildenv
& .\.buildenv\Scripts\python.exe -m pip install --upgrade pip
& .\.buildenv\Scripts\python.exe -m pip install "pyinstaller>=6.0,<7.0"
& .\.buildenv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --name AutonomousPlantViewer plant_viewer.py
Write-Host "Build output: $PSScriptRoot\dist\AutonomousPlantViewer.exe"
Write-Host "Not signed. Not a production OT controller. Validate on target Windows versions."
