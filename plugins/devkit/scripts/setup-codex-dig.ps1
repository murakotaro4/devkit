[CmdletBinding()]
param(
  [switch]$SkipInstall,
  [switch]$RegisterDailyTask,
  [string]$TaskTime = "07:00"
)

$ErrorActionPreference = "Stop"

Write-Warning "setup-codex-dig.ps1 is deprecated. Use devkit-setup.ps1 instead."

$target = Join-Path $PSScriptRoot "devkit-setup.ps1"
if (-not (Test-Path -LiteralPath $target)) {
  throw "MISSING_NEW_SETUP_SCRIPT: $target"
}

$args = @()
if ($SkipInstall) { $args += "-SkipInstall" }
if ($RegisterDailyTask) { $args += "-RegisterDailyTask" }
$args += @("-TaskTime", $TaskTime)

& powershell -NoProfile -ExecutionPolicy Bypass -File $target @args
exit $LASTEXITCODE
