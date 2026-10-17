# User-owned code signing certificate required. Never produces a fake publisher identity.
param(
    [Parameter(Mandatory=$true)][string]$CertificateThumbprint,
    [string]$ExePath = '.\dist\AutonomousPlantSimulatorV20\AutonomousPlantSimulatorV20.exe'
)
$ErrorActionPreference='Stop'
$cmd=Get-Command signtool.exe -ErrorAction SilentlyContinue
if (-not $cmd) {throw 'signtool.exe from Windows SDK is required.'}
$cert=Get-ChildItem Cert:\CurrentUser\My | Where-Object Thumbprint -eq $CertificateThumbprint | Select-Object -First 1
if (-not $cert -or -not $cert.HasPrivateKey) {throw 'A valid private-key code-signing certificate is required.'}
if (-not (Test-Path $ExePath)) {throw 'Native Windows EXE not found.'}
& $cmd.Source sign /fd SHA256 /sha1 $CertificateThumbprint /tr 'http://timestamp.digicert.com' /td SHA256 $ExePath
if ($LASTEXITCODE -ne 0) {throw 'Signing failed. Do not distribute as signed.'}
$signature=Get-AuthenticodeSignature -FilePath $ExePath
if ($signature.Status -ne 'Valid') {throw "Authenticode signature not trusted: $($signature.Status)"}
Write-Host 'AUTHENTICODE VALID for selected signed EXE; DOES NOT grant OT/site certification.'
