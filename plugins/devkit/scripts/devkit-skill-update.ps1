[CmdletBinding()]
param(
  [switch]$SimulateFailure
)

$ErrorActionPreference = "Stop"

$UserHome = $env:USERPROFILE
$CodexRoot = Join-Path $UserHome ".codex"
$CodexLogs = Join-Path $CodexRoot "logs"
$LogPath = Join-Path $CodexLogs "devkit-skill-update.log"
$StatusPath = Join-Path $CodexLogs "devkit-skill-update-status.json"

. (Join-Path $PSScriptRoot "devkit-runtime-sync.ps1")

function Log([string]$Message) {
  $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
  Add-Content -LiteralPath $LogPath -Value $line -Encoding UTF8
  Write-Host $line
}

function Write-Status([string]$Status, [string]$Message, [int]$ExitCode) {
  $payload = [ordered]@{
    status = $Status
    message = $Message
    exitCode = $ExitCode
    timestamp = (Get-Date -Format "o")
  }
  $json = $payload | ConvertTo-Json -Depth 3
  Set-Content -LiteralPath $StatusPath -Value $json -Encoding UTF8
}

Ensure-DevKitDir $CodexLogs

$runtimeErrors = New-Object System.Collections.Generic.List[string]
$logger = {
  param($Message)
  Log $Message
}

try {
  Log "Update started."

  if ($SimulateFailure) {
    throw "SIMULATED_FAILURE"
  }

  try {
    $codexResult = Sync-DevKitCodexRuntime -UserHome $UserHome -Logger $logger -RefreshConfig
    Log ("Codex runtime synced from: " + $codexResult.SourceRoot)
    if ($codexResult.ConfigResult.BootstrappedLocalOverlay) {
      Log "Bootstrapped local Codex overlay from the existing config."
    }
    if ($codexResult.ConfigResult.BackupPath) {
      Log ("Codex config backup saved: " + $codexResult.ConfigResult.BackupPath)
    }
    if ($codexResult.ConfigResult.UsedLocalOverlay) {
      Log ("Applied local Codex overlay: " + $codexResult.ConfigResult.LocalOverlayPath)
    }
    Log "Codex config refreshed."
  } catch {
    $runtimeErrors.Add("codex: " + $_.Exception.Message) | Out-Null
    Log ("Codex runtime sync failed: " + $_.Exception.Message)
  }

  try {
    $opencodeResult = Sync-DevKitOpenCodeRuntime -UserHome $UserHome -Logger $logger
    Log ("OpenCode runtime synced from: " + $opencodeResult.SourceRoot)
  } catch {
    $runtimeErrors.Add("opencode: " + $_.Exception.Message) | Out-Null
    Log ("OpenCode runtime sync failed: " + $_.Exception.Message)
  }

  if ($runtimeErrors.Count -eq 0) {
    Write-Status -Status "ok" -Message "DevKit runtime sync succeeded for Codex and OpenCode." -ExitCode 0
    exit 0
  }

  $message = "DevKit runtime sync completed with errors: " + ($runtimeErrors -join "; ")
  Write-Status -Status "warn" -Message $message -ExitCode 2
  exit 2
} catch {
  $rootError = $_.Exception.Message
  Log ("Update failed: " + $rootError)
  Write-Status -Status "failed" -Message ("DevKit runtime sync failed: " + $rootError) -ExitCode 1
  exit 1
}
