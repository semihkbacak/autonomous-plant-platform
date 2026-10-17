# FIX11.1 / One-point cross-platform self-test repair.
# Put this file and FIX11_1_ONAR.cmd into your existing FIX11 PROJECT ROOT.
# No administrator rights needed; does not touch Windows security settings.
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
Set-Location -LiteralPath $root
$target = Join-Path $root 'desktop\full_simulator_launcher.py'
$py = Join-Path $root '.venv\Scripts\python.exe'
$tests = Join-Path $root 'tests\test_fix11_frozen_sql_resources.py'
$old = 'missing_assets = [str(item.relative_to(base)) for item in essential_assets if not item.is_file()]'
$new = 'missing_assets = [item.relative_to(base).as_posix() for item in essential_assets if not item.is_file()]'
try {
    Write-Host '[FIX11.1] Checking project path...' -ForegroundColor Cyan
    if (!(Test-Path -LiteralPath (Join-Path $root '06_WINDOWS_TAM_EXE_DERLE.cmd'))) { throw 'FIX11 project root not found. Copy both FIX11_1 repair files NEXT TO 06_WINDOWS_TAM_EXE_DERLE.cmd.' }
    if (!(Test-Path -LiteralPath $target)) { throw ('Missing launcher file: ' + $target) }
    if (!(Test-Path -LiteralPath $py)) { throw 'Windows .venv missing. Run 02_YALNIZ_TEST.cmd first.' }
    $code = [System.IO.File]::ReadAllText($target, [System.Text.Encoding]::UTF8)
    if ($code.Contains($old)) {
        # Repair backups must NEVER be stored beneath the pytest project root.
        $backupRoot = Join-Path (Split-Path -Parent $root) 'AutonomousPlant_RepairBackups'
        $stamp = [DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ')
        $backupDir = Join-Path $backupRoot (Join-Path $stamp 'desktop')
        [System.IO.Directory]::CreateDirectory($backupDir) | Out-Null
        $backup = Join-Path $backupDir 'full_simulator_launcher.py'
        [System.IO.File]::Copy($target, $backup, $false)
        $newCode = $code.Replace($old, $new)
        [System.IO.File]::WriteAllText($target, $newCode, (New-Object System.Text.UTF8Encoding($false)))
        Write-Host '[FIX11.1] Windows path separator fix applied. Original backed up.' -ForegroundColor Green
    } elseif ($code.Contains($new)) {
        Write-Host '[FIX11.1] The fix is already installed.' -ForegroundColor Green
    } else {
        throw 'Launcher code differs from FIX11 release. No changes made; use full FIX11.1 ZIP.'
    }
    Write-Host '[FIX11.1] Testing previously failing case...' -ForegroundColor Cyan
    & $py -m pytest -q --assert=plain --tb=short $tests
    if ($LASTEXITCODE -ne 0) { throw 'Resource test failed. See output.' }
    Write-Host '[FIX11.1] Checking GUI launcher headless self-test...' -ForegroundColor Cyan
    & $py -m desktop.full_simulator_launcher --self-test
    if ($LASTEXITCODE -ne 0) { throw 'Launcher self-test failed. See output.' }
    Write-Host '[FIX11.1] Repair validated. You can now run 06_WINDOWS_TAM_EXE_DERLE.cmd.' -ForegroundColor Green
} catch {
    Write-Host ('[FIX11.1] ERROR: '+ $_.Exception.Message) -ForegroundColor Red
    exit 1
}
exit 0
