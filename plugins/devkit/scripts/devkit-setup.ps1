[CmdletBinding()]
param(
  [switch]$SkipInstall,
  [switch]$RegisterDailyTask,
  [string]$TaskTime = "07:00"
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
$CodexBin = Join-Path $CodexRoot "bin"
$LocalBin = Join-Path $UserHome ".local\bin"
$CodexDevKit = Join-Path $CodexRoot "devkit"
$CodexDevKitTemplates = Join-Path $CodexDevKit "templates\codex"
$CodexDevKitSourceRoot = Join-Path $CodexDevKit "source-root.txt"
$CodexLogs = Join-Path $CodexRoot "logs"
$TaskName = "DevKitSkillsDailyUpdate"

function Write-Info([string]$Message) {
  Write-Host "[devkit] $Message"
}

function Ensure-Dir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
  }
}

function Is-ReparsePoint([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) { return $false }
  $item = Get-Item -LiteralPath $Path -Force
  return [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
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

function Test-SymlinkCapability {
  $probeRoot = Join-Path $env:TEMP ("devkit-link-probe-" + [guid]::NewGuid().ToString("N"))
  $src = Join-Path $probeRoot "src"
  $dst = Join-Path $probeRoot "dst"
  Ensure-Dir $probeRoot
  Ensure-Dir $src
  try {
    New-Item -ItemType SymbolicLink -Path $dst -Target $src -Force | Out-Null
    return $true
  } catch {
    return $false
  } finally {
    if (Test-Path -LiteralPath $probeRoot) {
      Remove-Item -LiteralPath $probeRoot -Recurse -Force -ErrorAction SilentlyContinue
    }
  }
}

function Ensure-AllowlistedSource([string]$SkillName) {
  $meta = Join-Path (Join-Path $AgentSkills $SkillName) ".openskills.json"
  if (-not (Test-Path -LiteralPath $meta)) {
    throw "MISSING_SOURCE_METADATA: $meta"
  }
  $raw = Get-Content -LiteralPath $meta -Raw -Encoding UTF8
  $json = $raw | ConvertFrom-Json
  $source = [string]$json.source
  if ([string]::IsNullOrWhiteSpace($source)) {
    throw "INVALID_SOURCE_METADATA: $meta"
  }
  if (-not ($source -eq $AllowedSource -or $source.StartsWith($AllowedSource))) {
    throw "SOURCE_NOT_ALLOWLISTED: $SkillName => $source"
  }
}

function Ensure-SkillLink([string]$SkillName, [bool]$CanSymlink) {
  $src = Join-Path $AgentSkills $SkillName
  $dst = Join-Path $CodexSkills $SkillName

  if (-not (Test-Path -LiteralPath $src)) {
    throw "MISSING_SKILL_SOURCE_DIR: $src"
  }

  if (Test-Path -LiteralPath $dst) {
    if (Is-ReparsePoint $dst) {
      Remove-Item -LiteralPath $dst -Recurse -Force
    } else {
      throw "BLOCKED_EXISTING_DIR: $dst`nRemediation: Rename-Item -LiteralPath '$dst' -NewName '$SkillName.backup.$(Get-Date -Format yyyyMMddHHmmss)'"
    }
  }

  if ($CanSymlink) {
    try {
      New-Item -ItemType SymbolicLink -Path $dst -Target $src -Force | Out-Null
    } catch {
      New-Item -ItemType Junction -Path $dst -Target $src -Force | Out-Null
    }
  } else {
    New-Item -ItemType Junction -Path $dst -Target $src -Force | Out-Null
  }

  $actual = Get-LinkTargetPath $dst
  $expected = Convert-ToFullPath $src
  if ($null -eq $actual -or $actual -ne $expected) {
    throw "LINK_TARGET_MISMATCH: $dst => actual '$actual' expected '$expected'"
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

function Register-DailyTask([string]$UpdaterPath, [string]$At) {
  $atTime = [datetime]::ParseExact($At, "HH:mm", $null)
  $action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$UpdaterPath`""
  $trigger = New-ScheduledTaskTrigger -Daily -At $atTime
  Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Description "Daily DevKit skill update for Codex dig runtime" -Force | Out-Null
}

try {
  Write-Info "Preparing DevKit setup for Codex on Windows PowerShell."

  Ensure-Dir $AgentSkills
  Ensure-Dir $CodexSkills
  Ensure-Dir $CodexBin
  Ensure-Dir $LocalBin
  Ensure-Dir $CodexLogs
  Ensure-Dir $CodexDevKitTemplates

  if (-not $SkipInstall) {
    Write-Info "Installing/updating skills from allowlisted source via OpenSkills."
    & npx "openskills@latest" "install" $AllowedSource "--global" "--universal" "-y"
    if ($LASTEXITCODE -ne 0) {
      throw "OPENSKILLS_INSTALL_FAILED: exit=$LASTEXITCODE"
    }
  }

  foreach ($skill in $SkillManifest) {
    Ensure-AllowlistedSource $skill
  }

  $canSymlink = Test-SymlinkCapability
  if ($canSymlink) {
    Write-Info "SymbolicLink is available."
  } else {
    Write-Info "SymbolicLink is unavailable. Junction fallback will be used."
  }

  foreach ($skill in $SkillManifest) {
    Ensure-SkillLink -SkillName $skill -CanSymlink $canSymlink
  }

  $updaterSrc = Join-Path $PSScriptRoot "devkit-skill-update.ps1"
  if (-not (Test-Path -LiteralPath $updaterSrc)) {
    throw "MISSING_UPDATER_SCRIPT: $updaterSrc"
  }
  $updaterDst = Join-Path $CodexBin "devkit-skill-update.ps1"
  Copy-DevKitTextFile -SourcePath $updaterSrc -DestinationPath $updaterDst

  $updateCcxPs1Src = Join-Path $PSScriptRoot "update-ccx.ps1"
  $updateCcxCmdSrc = Join-Path $PSScriptRoot "update-ccx.cmd"
  $updateCcxPs1Dst = Join-Path $CodexBin "update-ccx.ps1"
  $updateCcxCmdDst = Join-Path $CodexBin "update-ccx.cmd"
  Copy-DevKitTextFile -SourcePath $updateCcxPs1Src -DestinationPath $updateCcxPs1Dst
  Copy-DevKitTextFile -SourcePath $updateCcxCmdSrc -DestinationPath $updateCcxCmdDst
  Install-UpdateCcxShim -ShimDirectory $LocalBin -TargetCommandPath $updateCcxCmdDst
  if (Ensure-UserPathContains -PathEntry $LocalBin) {
    Write-Info "Added $LocalBin to the user PATH."
  }

  $configHelperSrc = Join-Path $PSScriptRoot "devkit-codex-config.ps1"
  $configHelperDst = Join-Path $CodexBin "devkit-codex-config.ps1"
  Copy-DevKitTextFile -SourcePath $configHelperSrc -DestinationPath $configHelperDst

  $templateSrcRoot = Join-Path (Split-Path -Parent $PSScriptRoot) "templates\codex"
  $pluginRoot = Split-Path -Parent $PSScriptRoot
  Copy-DevKitTextFile `
    -SourcePath (Join-Path $templateSrcRoot "config.shared.toml") `
    -DestinationPath (Join-Path $CodexDevKitTemplates "config.shared.toml")
  Copy-DevKitTextFile `
    -SourcePath (Join-Path $templateSrcRoot "config.windows.toml") `
    -DestinationPath (Join-Path $CodexDevKitTemplates "config.windows.toml")
  Write-Utf8NoBom -Path $CodexDevKitSourceRoot -Content ($pluginRoot + "`n")

  . $configHelperDst
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

  if ($RegisterDailyTask) {
    Write-Info "Registering scheduled task '$TaskName' at $TaskTime."
    Register-DailyTask -UpdaterPath $updaterDst -At $TaskTime
  }

  Write-Info "Setup completed."
  Write-Host ""
  Write-Host "Run dig from Codex:"
  Write-Host '  $dig <topic>'
  Write-Host ""
  Write-Host "Run update-ccx from PowerShell/cmd:"
  Write-Host "  update-ccx --version"
  Write-Host ""
  Write-Host "Manual update command:"
  Write-Host "  powershell -NoProfile -ExecutionPolicy Bypass -File `"$updaterDst`""
  exit 0
} catch {
  Write-Error $_
  exit 1
}
