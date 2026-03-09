[CmdletBinding()]
param(
  [switch]$SimulateFailure
)

$ErrorActionPreference = "Stop"

$AllowedSource = "git@github.com:murakotaro4/devkit.git"
$SkillManifest = @(
  "dig",
  "dig-core",
  "dig-claude",
  "dig-codex",
  "dig-opencode",
  "gpt-pro",
  "deep-research",
  "mermaid-show",
  "amazon-search",
  "improve-skill",
  "codex-search",
  "devkit-init"
)

$UserHome = $env:USERPROFILE
$AgentSkills = Join-Path $UserHome ".agent\skills"
$CodexRoot = Join-Path $UserHome ".codex"
$CodexBin = Join-Path $CodexRoot "bin"
$LocalBin = Join-Path $UserHome ".local\bin"
$CodexDevKit = Join-Path $CodexRoot "devkit"
$CodexDevKitTemplates = Join-Path $CodexDevKit "templates\codex"
$CodexDevKitSourceRoot = Join-Path $CodexDevKit "source-root.txt"
$CodexSkills = Join-Path $CodexRoot "skills"
$CodexLogs = Join-Path $CodexRoot "logs"
$BackupDir = Join-Path $CodexLogs "backups"
$LogPath = Join-Path $CodexLogs "devkit-skill-update.log"
$StatusPath = Join-Path $CodexLogs "devkit-skill-update-status.json"

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
  }
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Copy-DevKitTextFile([string]$SourcePath, [string]$DestinationPath) {
  if (-not (Test-Path -LiteralPath $SourcePath)) {
    throw "MISSING_SOURCE_FILE: $SourcePath"
  }
  $content = Get-Content -LiteralPath $SourcePath -Raw -Encoding UTF8
  Write-Utf8NoBom -Path $DestinationPath -Content $content
}

function Convert-ToFullPath([string]$Path) {
  if ([string]::IsNullOrWhiteSpace($Path)) {
    return $null
  }

  try {
    $expanded = [Environment]::ExpandEnvironmentVariables($Path)
    return [IO.Path]::GetFullPath($expanded).TrimEnd('\').ToLowerInvariant()
  } catch {
    return $expanded.TrimEnd('\').ToLowerInvariant()
  }
}

function Ensure-UserPathContains([string]$PathEntry) {
  $target = Convert-ToFullPath $PathEntry
  $currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $entries = @()
  if (-not [string]::IsNullOrWhiteSpace($currentUserPath)) {
    $entries = @($currentUserPath -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
  }

  $normalizedEntries = @($entries | ForEach-Object { Convert-ToFullPath $_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
  if ($normalizedEntries -contains $target) {
    return $false
  }

  $updatedEntries = @($entries + $PathEntry)
  [Environment]::SetEnvironmentVariable("Path", ($updatedEntries -join ';'), "User")
  if (-not ((($env:PATH -split ';' | ForEach-Object { Convert-ToFullPath $_ }) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -contains $target)) {
    $env:PATH = "$PathEntry;$env:PATH"
  }
  return $true
}

function Install-UpdateCcxShim([string]$ShimDirectory, [string]$TargetCommandPath) {
  Ensure-Dir $ShimDirectory
  $shimPath = Join-Path $ShimDirectory "update-ccx.cmd"
  $shimContent = @(
    "@echo off",
    "setlocal",
    "call `"$TargetCommandPath`" %*",
    "exit /b %ERRORLEVEL%"
  ) -join "`r`n"
  Write-Utf8NoBom -Path $shimPath -Content ($shimContent + "`r`n")
}

function Get-LinkTargetPath([string]$Path) {
  $item = Get-Item -LiteralPath $Path -Force
  $target = $item.Target
  if ($null -eq $target) { return $null }
  if ($target -is [array]) { $target = $target[0] }
  if ([string]::IsNullOrWhiteSpace([string]$target)) { return $null }
  if (-not [IO.Path]::IsPathRooted($target)) {
    $target = Join-Path (Split-Path -Parent $Path) $target
  }
  return Convert-ToFullPath $target
}

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

function Validate-AllowlistedSources {
  foreach ($skill in $SkillManifest) {
    $meta = Join-Path (Join-Path $AgentSkills $skill) ".openskills.json"
    if (-not (Test-Path -LiteralPath $meta)) {
      throw "MISSING_SOURCE_METADATA: $meta"
    }
    $raw = Get-Content -LiteralPath $meta -Raw -Encoding UTF8
    $obj = $raw | ConvertFrom-Json
    $source = [string]$obj.source
    if ([string]::IsNullOrWhiteSpace($source)) {
      throw "INVALID_SOURCE_METADATA: $meta"
    }
    if (-not ($source -eq $AllowedSource -or $source.StartsWith($AllowedSource))) {
      throw "SOURCE_NOT_ALLOWLISTED: $skill => $source"
    }
  }
}

function New-BackupZip {
  $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
  $zip = Join-Path $BackupDir ("skills-" + $stamp + ".zip")
  if (-not (Test-Path -LiteralPath $AgentSkills)) {
    throw "MISSING_AGENT_SKILLS_DIR: $AgentSkills"
  }
  Compress-Archive -Path (Join-Path $AgentSkills "*") -DestinationPath $zip -Force
  return $zip
}

function Restore-BackupZip([string]$ZipPath) {
  if (-not (Test-Path -LiteralPath $ZipPath)) {
    throw "MISSING_BACKUP_ZIP: $ZipPath"
  }
  $restoreRoot = Join-Path $env:TEMP ("devkit-restore-" + [guid]::NewGuid().ToString("N"))
  Ensure-Dir $restoreRoot
  Expand-Archive -LiteralPath $ZipPath -DestinationPath $restoreRoot -Force

  Ensure-Dir $AgentSkills
  Get-ChildItem -LiteralPath $AgentSkills -Force -ErrorAction SilentlyContinue | Remove-Item -Recurse -Force
  Get-ChildItem -LiteralPath $restoreRoot -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $AgentSkills -Recurse -Force
  }
  Remove-Item -LiteralPath $restoreRoot -Recurse -Force -ErrorAction SilentlyContinue
}

function Validate-SkillLinks {
  foreach ($skill in $SkillManifest) {
    $dst = Join-Path $CodexSkills $skill
    $src = Join-Path $AgentSkills $skill
    if (-not (Test-Path -LiteralPath $dst)) {
      throw "MISSING_CODEX_LINK: $dst"
    }
    $actual = Get-LinkTargetPath $dst
    $expected = Convert-ToFullPath $src
    if ($null -eq $actual -or $actual -ne $expected) {
      throw "LINK_TARGET_MISMATCH: $dst => actual '$actual' expected '$expected'"
    }
  }
}

function Sync-DevKitCodexAssets {
  if (-not (Test-Path -LiteralPath $CodexDevKitSourceRoot)) {
    return $false
  }

  $sourceRoot = (Get-Content -LiteralPath $CodexDevKitSourceRoot -Raw -Encoding UTF8).Trim()
  if ([string]::IsNullOrWhiteSpace($sourceRoot)) {
    return $false
  }

  $sourceScripts = Join-Path $sourceRoot "scripts"
  $sourceTemplates = Join-Path $sourceRoot "templates\codex"
  $required = @(
    (Join-Path $sourceScripts "devkit-codex-config.ps1"),
    (Join-Path $sourceScripts "devkit-skill-update.ps1"),
    (Join-Path $sourceScripts "update-ccx.ps1"),
    (Join-Path $sourceScripts "update-ccx.cmd"),
    (Join-Path $sourceTemplates "config.shared.toml"),
    (Join-Path $sourceTemplates "config.windows.toml")
  )

  foreach ($path in $required) {
    if (-not (Test-Path -LiteralPath $path)) {
      return $false
    }
  }

  Ensure-Dir $CodexBin
  Ensure-Dir $LocalBin
  Ensure-Dir $CodexDevKitTemplates

  Copy-DevKitTextFile `
    -SourcePath (Join-Path $sourceScripts "devkit-codex-config.ps1") `
    -DestinationPath (Join-Path $CodexBin "devkit-codex-config.ps1")
  Copy-DevKitTextFile `
    -SourcePath (Join-Path $sourceScripts "devkit-skill-update.ps1") `
    -DestinationPath (Join-Path $CodexBin "devkit-skill-update.ps1")
  Copy-DevKitTextFile `
    -SourcePath (Join-Path $sourceScripts "update-ccx.ps1") `
    -DestinationPath (Join-Path $CodexBin "update-ccx.ps1")
  Copy-DevKitTextFile `
    -SourcePath (Join-Path $sourceScripts "update-ccx.cmd") `
    -DestinationPath (Join-Path $CodexBin "update-ccx.cmd")
  Install-UpdateCcxShim -ShimDirectory $LocalBin -TargetCommandPath (Join-Path $CodexBin "update-ccx.cmd")
  [void](Ensure-UserPathContains -PathEntry $LocalBin)
  Copy-DevKitTextFile `
    -SourcePath (Join-Path $sourceTemplates "config.shared.toml") `
    -DestinationPath (Join-Path $CodexDevKitTemplates "config.shared.toml")
  Copy-DevKitTextFile `
    -SourcePath (Join-Path $sourceTemplates "config.windows.toml") `
    -DestinationPath (Join-Path $CodexDevKitTemplates "config.windows.toml")

  return $true
}

Ensure-Dir $CodexLogs
Ensure-Dir $BackupDir

$backupZip = $null
try {
  Log "Update started."
  Validate-AllowlistedSources
  Log "Allowlisted source verification passed."

  $backupZip = New-BackupZip
  Log ("Backup created: " + $backupZip)

  if (Sync-DevKitCodexAssets) {
    Log "Refreshed Codex config helper/templates from the DevKit source checkout."
  }

  if ($SimulateFailure) {
    throw "SIMULATED_FAILURE"
  }

  & npx "openskills@latest" "update" @SkillManifest
  if ($LASTEXITCODE -ne 0) {
    throw "OPENSKILLS_UPDATE_FAILED: exit=$LASTEXITCODE"
  }
  Log "OpenSkills update completed."

  Validate-SkillLinks
  Log "Post-update validation passed."

  try {
    $configHelperPath = Join-Path $CodexBin "devkit-codex-config.ps1"
    if (-not (Test-Path -LiteralPath $configHelperPath)) {
      throw "MISSING_CONFIG_HELPER: $configHelperPath"
    }

    . $configHelperPath
    $configResult = Install-DevKitCodexConfig -UserHome $UserHome -OsName "windows"
    if ($configResult.BootstrappedLocalOverlay) {
      Log "Bootstrapped local Codex overlay from the existing config."
    }
    if ($configResult.BackupPath) {
      Log ("Codex config backup saved: " + $configResult.BackupPath)
    }
    if ($configResult.UsedLocalOverlay) {
      Log ("Applied local Codex overlay: " + $configResult.LocalOverlayPath)
    }
    Log "Codex config refreshed."
  } catch {
    $configError = $_.Exception.Message
    Log ("Codex config refresh failed: " + $configError)
    Write-Status -Status "warn" -Message ("Skills updated, but Codex config was restored after refresh failure: " + $configError) -ExitCode 4
    exit 4
  }

  Write-Status -Status "ok" -Message "Update successful. Codex config refreshed." -ExitCode 0
  exit 0
} catch {
  $rootError = $_.Exception.Message
  Log ("Update failed: " + $rootError)

  $rolledBack = $false
  if ($backupZip) {
    try {
      Restore-BackupZip -ZipPath $backupZip
      $rolledBack = $true
      Log "Rollback completed from backup."
    } catch {
      Log ("Rollback failed: " + $_.Exception.Message)
      Write-Status -Status "rollback_failed" -Message ("Update failed and rollback failed: " + $rootError) -ExitCode 3
      exit 3
    }
  }

  if ($rolledBack) {
    Write-Status -Status "rolled_back" -Message ("Update failed and rollback completed: " + $rootError) -ExitCode 2
    exit 2
  }

  Write-Status -Status "warn" -Message ("Update failed before backup: " + $rootError) -ExitCode 1
  exit 1
}
