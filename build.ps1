[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$projectRoot = $PSScriptRoot
$pyinstaller = Join-Path $projectRoot ".venv\Scripts\pyinstaller.exe"
$spec = Join-Path $projectRoot "countdown_app.spec"
$workPath = Join-Path $projectRoot ".pyinstaller-build"
$distPath = Join-Path $projectRoot "dist"
$outputExe = Join-Path $distPath "CountdownApp.exe"
$outputDir = Split-Path -Parent $outputExe
$legacyOutputDir = Join-Path $distPath "CountdownApp"
$legacyOutputExe = Join-Path $legacyOutputDir "CountdownApp.exe"

if (-not (Test-Path -LiteralPath $pyinstaller -PathType Leaf)) {
    throw "PyInstaller was not found in .venv. Run: .\.venv\Scripts\python -m pip install -r requirements-dev.txt"
}

$runningApp = Get-CimInstance Win32_Process | Where-Object {
    $_.ExecutablePath -in @($outputExe, $legacyOutputExe)
}
if ($runningApp) {
    $processIds = ($runningApp.ProcessId -join ", ")
    throw "CountdownApp is still running from dist (PID: $processIds). Exit it from the system tray, then build again."
}

$preserveRoot = Join-Path ([IO.Path]::GetTempPath()) (
    "CountdownApp-build-preserve-" + [guid]::NewGuid().ToString("N")
)
$preserveNames = @("settings.json", "Logs")
New-Item -ItemType Directory -Path $preserveRoot | Out-Null
$buildExitCode = 1
try {
    foreach ($name in $preserveNames) {
        foreach ($candidateDir in @($outputDir, $legacyOutputDir)) {
            $source = Join-Path $candidateDir $name
            if (Test-Path -LiteralPath $source) {
                Copy-Item -LiteralPath $source -Destination $preserveRoot -Recurse -Force
                break
            }
        }
    }

    if (Test-Path -LiteralPath $legacyOutputDir) {
        $resolvedLegacy = [IO.Path]::GetFullPath($legacyOutputDir)
        $resolvedDist = [IO.Path]::GetFullPath($distPath)
        if ([IO.Path]::GetDirectoryName($resolvedLegacy) -ne $resolvedDist) {
            throw "Refusing to remove an unexpected legacy output directory: $resolvedLegacy"
        }
        Remove-Item -LiteralPath $resolvedLegacy -Recurse -Force
    }

    & $pyinstaller `
        --noconfirm `
        --clean `
        --workpath $workPath `
        --distpath $distPath `
        $spec
    $buildExitCode = $LASTEXITCODE
}
finally {
    New-Item -ItemType Directory -Path $outputDir -Force | Out-Null
    foreach ($name in $preserveNames) {
        $saved = Join-Path $preserveRoot $name
        if (Test-Path -LiteralPath $saved) {
            Copy-Item -LiteralPath $saved -Destination $outputDir -Recurse -Force
        }
    }
    $resolvedPreserve = [IO.Path]::GetFullPath($preserveRoot)
    $resolvedTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
    if ($resolvedPreserve.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase)) {
        Remove-Item -LiteralPath $resolvedPreserve -Recurse -Force
    }
}

if ($buildExitCode -ne 0) {
    throw "PyInstaller failed with exit code $buildExitCode."
}

if (-not (Test-Path -LiteralPath $outputExe -PathType Leaf)) {
    throw "Build finished without the expected executable: $outputExe"
}

Write-Host ""
Write-Host "Build complete. Run this executable:" -ForegroundColor Green
Write-Host $outputExe -ForegroundColor Cyan
Write-Host ""
Write-Warning "Only distribute dist\CountdownApp.exe. Do not run executables from .pyinstaller-build."
