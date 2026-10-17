param([string]$LogPath = '')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $root
$logFile = if ($LogPath) { $LogPath } else { Join-Path $root 'WINDOWS_EXE_DERLEME_RAPORU.txt' }
$logDir = Split-Path -Parent $logFile
if ($logDir -and -not (Test-Path $logDir)) { New-Item -ItemType Directory -Force -Path $logDir | Out-Null }
$transcriptStarted = $false
$exitCode = 1
try {
    Start-Transcript -Path $logFile -Force | Out-Null
    $transcriptStarted = $true
    Write-Host '[APP] Building LOCAL synthetic simulator for Windows (UNSIGNED).'
    Write-Host ('[APP] Build log: ' + $logFile)
    Write-Host ('[APP] Project folder: ' + $root)
    $py = Join-Path $root '.venv\Scripts\python.exe'
    if (!(Test-Path $py)) { throw 'Windows Python environment is missing. First run 01_WINDOWS_KUR_TEST_VE_BASLAT.cmd after extracting ZIP.' }
    & $py -m pip install 'pyinstaller==6.16.0'
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller installation failed. See log above.' }
    # The EXE must never be shipped if Windows regression tests still fail.
    $testTemp = Join-Path $root '.windows_test_tmp'
    New-Item -ItemType Directory -Force -Path $testTemp | Out-Null
    Write-Host '[APP] Running complete Windows regression before native EXE build...'
    & $py -m pytest -q --assert=plain --tb=short --basetemp=.windows_test_tmp/pytest_exe_prebuild
    if ($LASTEXITCODE -ne 0) { throw 'Windows regression tests failed; EXE build aborted.' }
    & $py -m desktop.full_simulator_launcher --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Desktop self-test failed. See log above.' }
    # PyInstaller resolves --add-data relative to --specpath, not the
    # project current working directory. Build ABSOLUTE input paths to avoid
    # searching for app/static under .build_full_v20 on Windows.
    $staticSrc = Join-Path $root 'app\static'
    $modelsSrc = Join-Path $root 'models'
    $solarSrc = Join-Path $root 'data\solar'
    $entrySrc = Join-Path $root 'desktop\full_simulator_launcher.py'
    $schemaSrc = Join-Path $root 'simulator\solar\ges_history_schema.sql'
    foreach ($assetPath in @($staticSrc, $modelsSrc, $solarSrc, $schemaSrc, $entrySrc)) {
        if (!(Test-Path -LiteralPath $assetPath)) {
            throw ('Missing EXE build input: ' + $assetPath + '. Extract the entire ZIP.')
        }
    }
    Write-Host '[APP] Verified absolute EXE resources: app/static, models, data/solar, ges_history_schema.sql, launcher.'
    $buildArgs = @(
        '-m','PyInstaller','--noconfirm','--clean','--onedir','--windowed',
        '--name','AutonomousPlantSimulatorV20_FIX11',
        '--paths',$root,
        '--distpath',(Join-Path $root 'dist'),
        '--workpath',(Join-Path $root '.build_full_v20'),
        '--specpath',(Join-Path $root '.build_full_v20'),
        '--collect-all','uvicorn','--collect-all','pvlib','--collect-all','sklearn',
        '--collect-all','scipy','--collect-all','pandas','--collect-all','openpyxl',
        '--collect-all','fastapi','--collect-all','starlette','--collect-all','pydantic',
        '--collect-submodules','app','--collect-submodules','core',
        '--collect-submodules','simulator','--collect-submodules','stage1','--collect-submodules','advanced_v2','--collect-submodules','research_v2',
        '--collect-submodules','tools',
        '--hidden-import','demo_ges_integrated_v04',
        '--hidden-import','demo_ges_timeseries',
        '--add-data',($staticSrc + ';app/static'),
        '--add-data',($modelsSrc + ';models'),
        '--add-data',($solarSrc + ';data/solar'),
        '--add-data',($schemaSrc + ';simulator/solar'),
        $entrySrc
    )
    Write-Host '[APP] Starting native Windows PyInstaller build. This can take several minutes.'
    & $py @buildArgs
    if ($LASTEXITCODE -ne 0) { throw ('Native Windows build failed, exit code ' + $LASTEXITCODE) }
    $exe = Join-Path $root 'dist\AutonomousPlantSimulatorV20_FIX11\AutonomousPlantSimulatorV20_FIX11.exe'
    if (!(Test-Path $exe)) { throw ('Build finished but EXE was not found: ' + $exe) }
    # PYINSTALLER PACKAGE INTEGRITY GATE: do not trust exit code alone.
    # A --windowed EXE cannot create SQLite history without this SQL schema.
    $bundledSchema = Join-Path $root 'dist\AutonomousPlantSimulatorV20_FIX11\_internal\simulator\solar\ges_history_schema.sql'
    if (!(Test-Path -LiteralPath $bundledSchema -PathType Leaf)) {
        throw ('Bundled SQL schema is missing: ' + $bundledSchema + '. Refuse to ship incomplete EXE.')
    }
    $sourceSchemaHash = (Get-FileHash -LiteralPath $schemaSrc -Algorithm SHA256).Hash
    $bundledSchemaHash = (Get-FileHash -LiteralPath $bundledSchema -Algorithm SHA256).Hash
    if ($sourceSchemaHash -ne $bundledSchemaHash) {
        throw ('Bundled SQL schema has incorrect contents: ' + $bundledSchema)
    }
    Write-Host '[APP] Native EXE schema asset present; SHA256 matches source.'
    Write-Host '[APP] Native bundled EXE dependency + PV/wind engine self-test...' 
    & $exe --self-test
    if ($LASTEXITCODE -ne 0) { throw ('Bundled EXE failed its native self-test: ' + $LASTEXITCODE) }
    Write-Host '[APP] Native EXE launching embedded ASGI / Uvicorn smoke test on ephemeral loopback port...'
    & $exe --smoke-server
    if ($LASTEXITCODE -ne 0) { throw ('Bundled EXE failed to run real Uvicorn HTTP server: ' + $LASTEXITCODE) }
    $hash = (Get-FileHash $exe -Algorithm SHA256).Hash
    Set-Content -Path (Join-Path (Split-Path $exe -Parent) 'SHA256.txt') -Value ($hash + '  AutonomousPlantSimulatorV20_FIX11.exe') -Encoding ascii
    Write-Host '[APP] Windows EXE build PASSED. Actual graphical start still requires user validation.' -ForegroundColor Green
    Write-Host ('[APP] EXE: ' + $exe) -ForegroundColor Green
    Write-Host '[APP] Keep the entire dist\AutonomousPlantSimulatorV20_FIX11 folder including _internal!'
    try {
        $desktop = [Environment]::GetFolderPath('Desktop')
        if ($desktop) {
            $shortcut = Join-Path $desktop 'Autonomous Plant Simulator UTC Stage1.lnk'
            $wsh = New-Object -ComObject WScript.Shell
            $link = $wsh.CreateShortcut($shortcut)
            $link.TargetPath = $exe
            $link.WorkingDirectory = $root
            $link.Description = 'Local synthetic HES/GES/RES simulator only (no OT connection)'
            $link.Save()
            Write-Host ('[APP] Desktop shortcut: ' + $shortcut)
        }
    } catch {
        Write-Warning ('Could not create Desktop shortcut: ' + $_.Exception.Message)
    }
    $exitCode = 0
} catch {
    Write-Host ('[APP] BUILD FAILED: ' + $_.Exception.Message) -ForegroundColor Red
    Write-Host '[APP] Save/send WINDOWS_EXE_DERLEME_RAPORU.txt for diagnosis.'
} finally {
    if ($transcriptStarted) { Stop-Transcript | Out-Null }
}
exit $exitCode
