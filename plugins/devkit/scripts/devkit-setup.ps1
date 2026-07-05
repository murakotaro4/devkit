[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"

$UserHome = $env:USERPROFILE

. (Join-Path $PSScriptRoot "devkit-lib.ps1")

function Write-Info([string]$Message) {
  Write-Host "[devkit] $Message"
}

function Get-DevKitSetupRepoRoot {
  $repoRoot = Resolve-DevKitRepoRootFromHint (Join-Path $PSScriptRoot "..\..\..")
  if (-not [string]::IsNullOrWhiteSpace($repoRoot)) {
    return $repoRoot
  }

  $logger = {
    param($Message)
    Write-Info $Message
  }
  return Get-DevKitRepoRoot -UserHome $UserHome -Logger $logger
}

try {
  Write-Info "Preparing DevKit for Codex."

  $repoRoot = Get-DevKitSetupRepoRoot
  $managed = Install-DevKitManagedFiles -RepoRoot $repoRoot -UserHome $UserHome

  $logger = {
    param($Message)
    Write-Info $Message
  }
  Remove-DevKitLegacyAssets -UserHome $UserHome -SourceRoot $repoRoot -Logger $logger

  . (Join-Path $managed.CodexBin "devkit-codex-config.ps1")
  $configResult = Install-DevKitCodexConfig -UserHome $UserHome -OsName "windows"

  if ($configResult.BootstrappedLocalOverlay) {
    Write-Info "Bootstrapped local Codex overlay from the existing config."
  }
  if ($configResult.BackupPath) {
    Write-Info "Codex config backup saved to: $($configResult.BackupPath)"
  }
  if ($configResult.UsedLocalOverlay) {
    Write-Info "Applied local Codex overlay: $($configResult.LocalOverlayPath)"
  }

  Write-Info "Codex config refreshed."
  Write-Info ("DevKit source: " + $repoRoot)
  Write-Info "Setup completed."
  Write-Host ""
  Write-Host "Run DevKit updates from PowerShell/cmd:"
  Write-Host "  update-devkit"
  Write-Host "  update-ccx"
  Write-Host ""
  Write-Host "Manual update command:"
  Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File `"$($managed.CodexBin)\update-devkit.ps1`" --devkit-only"
  exit 0
} catch {
  Write-Error $_
  exit 1
}
