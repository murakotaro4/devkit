[CmdletBinding()]
param(
  [switch]$RegisterDailyTask,
  [string]$TaskTime = "07:00"
)

$ErrorActionPreference = "Stop"

$UserHome = $env:USERPROFILE
$CodexRoot = Join-Path $UserHome ".codex"
$CodexBin = Join-Path $CodexRoot "bin"
$LocalBin = Join-Path $UserHome ".local\bin"
$TaskName = "DevKitSkillsDailyUpdate"

. (Join-Path $PSScriptRoot "devkit-runtime-sync.ps1")

function Write-Info([string]$Message) {
  Write-Host "[devkit] $Message"
}

function Copy-BootstrapScript([string]$Name) {
  $sourcePath = Join-Path $PSScriptRoot $Name
  $destinationPath = Join-Path $CodexBin $Name
  Copy-DevKitTextFile -SourcePath $sourcePath -DestinationPath $destinationPath
}

function Register-DailyTask([string]$UpdaterPath, [string]$At) {
  $atTime = [datetime]::ParseExact($At, "HH:mm", $null)
  $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$UpdaterPath`""
  $trigger = New-ScheduledTaskTrigger -Daily -At $atTime
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description "Daily DevKit runtime sync for Codex/OpenCode" -Force | Out-Null
}

try {
  Write-Info "Preparing DevKit runtime sync for Codex and OpenCode."

  Ensure-DevKitDir $CodexBin
  Ensure-DevKitDir $LocalBin

  foreach ($fileName in @(
    "devkit-runtime-sync.ps1",
    "devkit-codex-config.ps1",
    "devkit-skill-update.ps1",
    "update-ccx.ps1",
    "update-ccx.cmd",
    "update-ccx.sh",
    "update-devkit.ps1",
    "update-devkit.cmd",
    "update-devkit.sh"
  )) {
    Copy-BootstrapScript -Name $fileName
  }

  Install-DevKitCommandShim -ShimPath (Join-Path $LocalBin "update-ccx.cmd") -TargetCommandPath (Join-Path $CodexBin "update-ccx.cmd")
  Install-DevKitCommandShim -ShimPath (Join-Path $LocalBin "update-devkit.cmd") -TargetCommandPath (Join-Path $CodexBin "update-devkit.cmd")
  if (Ensure-DevKitUserPathContains -PathEntry $LocalBin) {
    Write-Info "Added $LocalBin to the user PATH."
  }

  $logger = {
    param($Message)
    Write-Info $Message
  }

  $codexResult = Sync-DevKitCodexRuntime -UserHome $UserHome -Logger $logger -RefreshConfig
  $opencodeResult = Sync-DevKitOpenCodeRuntime -UserHome $UserHome -Logger $logger

  if ($codexResult.ConfigResult.BootstrappedLocalOverlay) {
    Write-Info "Bootstrapped local Codex overlay from the existing config."
  }
  if ($codexResult.ConfigResult.BackupPath) {
    Write-Info "Codex config backup saved to: $($codexResult.ConfigResult.BackupPath)"
  }
  if ($codexResult.ConfigResult.UsedLocalOverlay) {
    Write-Info "Applied local Codex overlay: $($codexResult.ConfigResult.LocalOverlayPath)"
  }
  Write-Info "Codex config refreshed."
  Write-Info ("DevKit source: " + $codexResult.SourceRoot)
  Write-Info ("OpenCode sync source: " + $opencodeResult.SourceRoot)

  if ($RegisterDailyTask) {
    $updaterPath = Join-Path $CodexBin "devkit-skill-update.ps1"
    Write-Info "Registering scheduled task '$TaskName' at $TaskTime."
    Register-DailyTask -UpdaterPath $updaterPath -At $TaskTime
  }

  Write-Info "Setup completed."
  Write-Host ""
  Write-Host "Run DevKit sync from PowerShell/cmd:"
  Write-Host "  update-devkit"
  Write-Host "  update-ccx"
  Write-Host ""
  Write-Host "Run dig from Codex:"
  Write-Host '  $dig <topic>'
  Write-Host ""
  Write-Host "Manual update command:"
  Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File `"$($CodexBin)\update-devkit.ps1`" --devkit-only"
  exit 0
} catch {
  Write-Error $_
  exit 1
}
