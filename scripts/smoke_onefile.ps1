[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,
    [string]$ExpectedVersion = "2.2.0",
    [int]$TimeoutSeconds = 30
)

$ErrorActionPreference = "Stop"
$sourceExe = (Resolve-Path -LiteralPath $Executable).Path
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$smokeDir = Join-Path $tempRoot (
    "CountdownApp-onefile-smoke-" + [guid]::NewGuid().ToString("N")
)
$resolvedSmoke = [IO.Path]::GetFullPath($smokeDir)
if (-not $resolvedSmoke.StartsWith($tempRoot, [StringComparison]::OrdinalIgnoreCase)) {
    throw "Refusing to use an unsafe smoke-test directory: $resolvedSmoke"
}

New-Item -ItemType Directory -Path $resolvedSmoke | Out-Null
$smokeExe = Join-Path $resolvedSmoke "CountdownApp.exe"
$logPath = Join-Path $resolvedSmoke "Logs\countdown.log"
$settingsPath = Join-Path $resolvedSmoke "settings.json"
Copy-Item -LiteralPath $sourceExe -Destination $smokeExe

try {
    Start-Process -FilePath $smokeExe -ArgumentList "--startup" -WindowStyle Hidden | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds($TimeoutSeconds)
    $started = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        if (Test-Path -LiteralPath $logPath) {
            $logText = Get-Content -LiteralPath $logPath -Raw -ErrorAction SilentlyContinue
            if ($logText -match "Application started") {
                $started = $true
                break
            }
        }
        Start-Sleep -Milliseconds 100
    }

    $actualVersion = (Get-Item -LiteralPath $smokeExe).VersionInfo.FileVersion
    if (-not $started) {
        throw "The onefile application did not finish starting within $TimeoutSeconds seconds."
    }
    if (-not (Test-Path -LiteralPath $settingsPath)) {
        throw "First launch did not create settings.json beside the executable."
    }
    if ($actualVersion -ne $ExpectedVersion) {
        throw "Expected file version $ExpectedVersion, found $actualVersion."
    }

    [pscustomobject]@{
        Started = $started
        SettingsCreated = $true
        LogsCreated = Test-Path -LiteralPath $logPath
        FileVersion = $actualVersion
        SizeMB = [math]::Round((Get-Item -LiteralPath $smokeExe).Length / 1MB, 1)
    }
}
finally {
    Get-CimInstance Win32_Process | Where-Object {
        $_.ExecutablePath -eq $smokeExe
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
    Start-Sleep -Milliseconds 500
    if (Test-Path -LiteralPath $resolvedSmoke) {
        Remove-Item -LiteralPath $resolvedSmoke -Recurse -Force
    }
}
