[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$pyinstaller = Join-Path $projectRoot ".venv\Scripts\pyinstaller.exe"
$spec = Join-Path $projectRoot "countdown_app.spec"
$workPath = Join-Path $projectRoot ".pyinstaller-build"
$distPath = Join-Path $projectRoot "dist"
$outputExe = Join-Path $distPath "CountdownApp\CountdownApp.exe"

if (-not (Test-Path -LiteralPath $pyinstaller -PathType Leaf)) {
    throw "PyInstaller was not found in .venv. Run: .\.venv\Scripts\python -m pip install -r requirements-dev.txt"
}

$runningApp = Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -eq $outputExe
}
if ($runningApp) {
    $processIds = ($runningApp.ProcessId -join ", ")
    throw "CountdownApp is still running from dist (PID: $processIds). Exit it from the system tray, then build again."
}

& $pyinstaller `
    --noconfirm `
    --clean `
    --workpath $workPath `
    --distpath $distPath `
    $spec

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE."
}

if (-not (Test-Path -LiteralPath $outputExe -PathType Leaf)) {
    throw "Build finished without the expected executable: $outputExe"
}

Write-Host ""
Write-Host "Build complete. Run this executable:" -ForegroundColor Green
Write-Host $outputExe -ForegroundColor Cyan
Write-Host ""
Write-Warning "Do not run executables from .pyinstaller-build; that directory contains incomplete intermediate files."
