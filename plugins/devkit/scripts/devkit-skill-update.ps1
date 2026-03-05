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

function Convert-ToFullPath([string]$Path) {
  return [IO.Path]::GetFullPath($Path).TrimEnd('\').ToLowerInvariant()
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

Ensure-Dir $CodexLogs
Ensure-Dir $BackupDir

$backupZip = $null
try {
  Log "Update started."
  Validate-AllowlistedSources
  Log "Allowlisted source verification passed."

  $backupZip = New-BackupZip
  Log ("Backup created: " + $backupZip)

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

  Write-Status -Status "ok" -Message "Update successful." -ExitCode 0
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
