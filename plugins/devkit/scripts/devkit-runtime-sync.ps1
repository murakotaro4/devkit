function Get-DevKitRepoUrl {
  if (-not [string]::IsNullOrWhiteSpace($env:DEVKIT_REPO_URL)) {
    return $env:DEVKIT_REPO_URL.Trim()
  }

  return "https://github.com/murakotaro4/devkit.git"
}

function Get-DevKitSkillManifest {
  return @(
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
}

function Ensure-DevKitDir([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
  }
}

function Write-DevKitUtf8NoBom([string]$Path, [string]$Content) {
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Read-DevKitTextFile([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    throw "MISSING_FILE: $Path"
  }

  return Get-Content -LiteralPath $Path -Raw -Encoding UTF8
}

function Copy-DevKitTextFile([string]$SourcePath, [string]$DestinationPath) {
  if (-not (Test-Path -LiteralPath $SourcePath)) {
    throw "MISSING_SOURCE_FILE: $SourcePath"
  }

  $content = Get-Content -LiteralPath $SourcePath -Raw -Encoding UTF8
  Write-DevKitUtf8NoBom -Path $DestinationPath -Content $content
}

function Convert-DevKitToFullPath([string]$Path) {
  if ([string]::IsNullOrWhiteSpace($Path)) {
    return $null
  }

  try {
    $expanded = [Environment]::ExpandEnvironmentVariables($Path)
    return [IO.Path]::GetFullPath($expanded).TrimEnd('\').ToLowerInvariant()
  } catch {
    return $Path.TrimEnd('\').ToLowerInvariant()
  }
}

function Convert-DevKitToMsysPath([string]$Path) {
  if ([string]::IsNullOrWhiteSpace($Path)) {
    return $null
  }

  $fullPath = [IO.Path]::GetFullPath($Path)
  if ($fullPath -match '^(?<drive>[A-Za-z]):\\(?<rest>.*)$') {
    $drive = $Matches.drive.ToLowerInvariant()
    $rest = $Matches.rest -replace '\\', '/'
    if ([string]::IsNullOrWhiteSpace($rest)) {
      return "/$drive"
    }
    return "/$drive/$rest"
  }

  return $fullPath -replace '\\', '/'
}

function Test-DevKitCommandAvailable([string]$Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-DevKitLogger([scriptblock]$Logger, [string]$Message) {
  if ($null -ne $Logger) {
    & $Logger $Message
  }
}

function Ensure-DevKitUserPathContains([string]$PathEntry) {
  $target = Convert-DevKitToFullPath $PathEntry
  $currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
  $entries = @()
  if (-not [string]::IsNullOrWhiteSpace($currentUserPath)) {
    $entries = @($currentUserPath -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
  }

  $normalizedEntries = @($entries | ForEach-Object { Convert-DevKitToFullPath $_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
  if ($normalizedEntries -contains $target) {
    return $false
  }

  $updatedEntries = @($entries + $PathEntry)
  [Environment]::SetEnvironmentVariable("Path", ($updatedEntries -join ';'), "User")
  if (-not ((($env:PATH -split ';' | ForEach-Object { Convert-DevKitToFullPath $_ }) | Where-Object { -not [string]::IsNullOrWhiteSpace($_) }) -contains $target)) {
    $env:PATH = "$PathEntry;$env:PATH"
  }
  return $true
}

function Install-DevKitCommandShim([string]$ShimPath, [string]$TargetCommandPath) {
  $shimDir = Split-Path -Parent $ShimPath
  Ensure-DevKitDir $shimDir
  $shimContent = @(
    "@echo off",
    "setlocal",
    "call `"$TargetCommandPath`" %*",
    "exit /b %ERRORLEVEL%"
  ) -join "`r`n"
  Write-DevKitUtf8NoBom -Path $ShimPath -Content ($shimContent + "`r`n")
}

function Install-DevKitShellShim([string]$ShimPath, [string]$TargetScriptPath) {
  $shimDir = Split-Path -Parent $ShimPath
  Ensure-DevKitDir $shimDir
  $shellTarget = Convert-DevKitToMsysPath $TargetScriptPath
  $shimContent = @(
    "#!/bin/bash",
    "set -euo pipefail",
    "exec `"$shellTarget`" `"$@`""
  ) -join "`n"
  Write-DevKitUtf8NoBom -Path $ShimPath -Content ($shimContent + "`n")
}

function Get-DevKitLinkTargetPath([string]$Path) {
  $item = Get-Item -LiteralPath $Path -Force
  $target = $item.Target
  if ($null -eq $target) { return $null }
  if ($target -is [array]) { $target = $target[0] }
  if ([string]::IsNullOrWhiteSpace([string]$target)) { return $null }
  if (-not [IO.Path]::IsPathRooted($target)) {
    $target = Join-Path (Split-Path -Parent $Path) $target
  }
  return Convert-DevKitToFullPath $target
}

function Test-DevKitReparsePoint([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    return $false
  }

  $item = Get-Item -LiteralPath $Path -Force
  return [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function Test-DevKitSymlinkCapability {
  $probeRoot = Join-Path $env:TEMP ("devkit-link-probe-" + [guid]::NewGuid().ToString("N"))
  $src = Join-Path $probeRoot "src"
  $dst = Join-Path $probeRoot "dst"
  Ensure-DevKitDir $probeRoot
  Ensure-DevKitDir $src
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

function Test-DevKitFileContentEqual([string]$LeftPath, [string]$RightPath) {
  if (-not (Test-Path -LiteralPath $LeftPath) -or -not (Test-Path -LiteralPath $RightPath)) {
    return $false
  }

  return (Read-DevKitTextFile -Path $LeftPath) -eq (Read-DevKitTextFile -Path $RightPath)
}

function Invoke-DevKitGit([string]$WorkingDirectory, [string[]]$Arguments) {
  if ([string]::IsNullOrWhiteSpace($WorkingDirectory)) {
    & git @Arguments | Out-Null
  } else {
    Push-Location $WorkingDirectory
    try {
      & git @Arguments | Out-Null
    } finally {
      Pop-Location
    }
  }

  if ($LASTEXITCODE -ne 0) {
    throw "GIT_COMMAND_FAILED: git $($Arguments -join ' ')"
  }
}

function Get-DevKitRepoRoot([string]$SourceRoot, [scriptblock]$Logger) {
  $pluginRoot = Join-Path $SourceRoot "plugins\devkit"
  if (Test-Path -LiteralPath $pluginRoot) {
    return $SourceRoot
  }

  throw "DEVKIT_PLUGIN_ROOT_NOT_FOUND: $pluginRoot"
}

function Ensure-DevKitSourceCheckout([string]$SourceRoot, [scriptblock]$Logger) {
  $repoUrl = Get-DevKitRepoUrl
  $gitDir = Join-Path $SourceRoot ".git"

  if (Test-Path -LiteralPath $gitDir) {
    if (-not (Test-DevKitCommandAvailable "git")) {
      Invoke-DevKitLogger $Logger "git is unavailable. Reusing the existing DevKit checkout."
      return (Get-DevKitRepoRoot -SourceRoot $SourceRoot -Logger $Logger)
    }

    Invoke-DevKitLogger $Logger ("Updating DevKit checkout: " + $SourceRoot)
    Invoke-DevKitGit -WorkingDirectory $SourceRoot -Arguments @("pull", "--ff-only")
    return (Get-DevKitRepoRoot -SourceRoot $SourceRoot -Logger $Logger)
  }

  if (Test-Path -LiteralPath $SourceRoot) {
    $existingChildren = @(Get-ChildItem -LiteralPath $SourceRoot -Force -ErrorAction SilentlyContinue)
    if ($existingChildren.Count -gt 0) {
      if (Test-Path -LiteralPath (Join-Path $SourceRoot "plugins\devkit")) {
        Invoke-DevKitLogger $Logger ("Using the existing DevKit source snapshot: " + $SourceRoot)
        return (Get-DevKitRepoRoot -SourceRoot $SourceRoot -Logger $Logger)
      }

      throw "DEVKIT_SOURCE_ROOT_NOT_EMPTY: $SourceRoot"
    }
  } else {
    $parent = Split-Path -Parent $SourceRoot
    Ensure-DevKitDir $parent
  }

  if (-not (Test-DevKitCommandAvailable "git")) {
    throw "DEVKIT_GIT_REQUIRED: git is required to fetch " + $repoUrl
  }

  Invoke-DevKitLogger $Logger ("Cloning DevKit checkout: " + $SourceRoot)
  Invoke-DevKitGit -WorkingDirectory $null -Arguments @("clone", "--depth", "1", $repoUrl, $SourceRoot)
  return (Get-DevKitRepoRoot -SourceRoot $SourceRoot -Logger $Logger)
}

function Assert-DevKitLegacySkillsRootMigratable([string]$LinkTarget) {
  if ([string]::IsNullOrWhiteSpace($LinkTarget)) {
    return
  }

  $known = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  foreach ($skill in (Get-DevKitSkillManifest)) {
    [void]$known.Add($skill)
  }

  if (-not (Test-Path -LiteralPath $LinkTarget)) {
    return
  }

  foreach ($entry in (Get-ChildItem -LiteralPath $LinkTarget -Force -ErrorAction SilentlyContinue)) {
    if ($entry.Name.StartsWith(".")) {
      continue
    }

    if (-not $known.Contains($entry.Name)) {
      throw "BLOCKED_LEGACY_SKILLS_ROOT: $LinkTarget contains non-DevKit entry '$($entry.Name)'. Remediation: move custom skills out of ~/.agent/skills before migrating OpenCode."
    }
  }
}

function Ensure-DevKitDirectoryContainer([string]$Path, [string]$ExpectedLegacyTarget = $null, [switch]$AssertLegacySkillRoot) {
  if (-not (Test-Path -LiteralPath $Path)) {
    Ensure-DevKitDir $Path
    return
  }

  if (-not (Test-DevKitReparsePoint $Path)) {
    if ((Get-Item -LiteralPath $Path -Force) -is [IO.DirectoryInfo]) {
      return
    }

    throw "BLOCKED_EXISTING_FILE: $Path"
  }

  $actual = Get-DevKitLinkTargetPath $Path
  $legacy = Convert-DevKitToFullPath $ExpectedLegacyTarget
  if ([string]::IsNullOrWhiteSpace($legacy) -or $actual -ne $legacy) {
    throw "BLOCKED_EXISTING_LINK: $Path => $actual"
  }

  if ($AssertLegacySkillRoot) {
    Assert-DevKitLegacySkillsRootMigratable -LinkTarget $ExpectedLegacyTarget
  }

  Remove-Item -LiteralPath $Path -Recurse -Force
  Ensure-DevKitDir $Path
}

function Ensure-DevKitLinkedDirectory([string]$SourcePath, [string]$DestinationPath, [bool]$CanSymlink, [string]$ExpectedLegacyTarget = $null) {
  if (-not (Test-Path -LiteralPath $SourcePath)) {
    throw "MISSING_SKILL_SOURCE_DIR: $SourcePath"
  }

  if (Test-Path -LiteralPath $DestinationPath) {
    if (Test-DevKitReparsePoint $DestinationPath) {
      $actual = Get-DevKitLinkTargetPath $DestinationPath
      $expected = Convert-DevKitToFullPath $SourcePath
      $legacy = Convert-DevKitToFullPath $ExpectedLegacyTarget
      if ($actual -ne $expected -and ([string]::IsNullOrWhiteSpace($legacy) -or $actual -ne $legacy)) {
        throw "BLOCKED_EXISTING_LINK: $DestinationPath => $actual"
      }

      Remove-Item -LiteralPath $DestinationPath -Recurse -Force
    } else {
      throw "BLOCKED_EXISTING_DIR: $DestinationPath"
    }
  }

  if ($CanSymlink) {
    try {
      New-Item -ItemType SymbolicLink -Path $DestinationPath -Target $SourcePath -Force | Out-Null
    } catch {
      New-Item -ItemType Junction -Path $DestinationPath -Target $SourcePath -Force | Out-Null
    }
  } else {
    New-Item -ItemType Junction -Path $DestinationPath -Target $SourcePath -Force | Out-Null
  }
}

function Ensure-DevKitManagedFile([string]$SourcePath, [string]$DestinationPath, [switch]$AllowDifferentExistingContent) {
  if (-not (Test-Path -LiteralPath $SourcePath)) {
    throw "MISSING_SOURCE_FILE: $SourcePath"
  }

  if (Test-Path -LiteralPath $DestinationPath) {
    if ((Get-Item -LiteralPath $DestinationPath -Force) -is [IO.DirectoryInfo]) {
      throw "BLOCKED_EXISTING_DIR: $DestinationPath"
    }

    if (-not $AllowDifferentExistingContent -and -not (Test-DevKitFileContentEqual -LeftPath $SourcePath -RightPath $DestinationPath)) {
      throw "BLOCKED_EXISTING_FILE: $DestinationPath"
    }
  }

  Copy-DevKitTextFile -SourcePath $SourcePath -DestinationPath $DestinationPath
}

function Sync-DevKitCodexRuntime([string]$UserHome, [scriptblock]$Logger, [switch]$RefreshConfig) {
  $codexRoot = Join-Path $UserHome ".codex"
  $codexSkills = Join-Path $codexRoot "skills"
  $codexBin = Join-Path $codexRoot "bin"
  $localBin = Join-Path $UserHome ".local\bin"
  $codexDevKit = Join-Path $codexRoot "devkit"
  $codexDevKitTemplates = Join-Path $codexDevKit "templates\codex"
  $codexSourceRoot = Join-Path $codexDevKit "source"
  $codexSourceRootFile = Join-Path $codexDevKit "source-root.txt"
  $repoRoot = Ensure-DevKitSourceCheckout -SourceRoot $codexSourceRoot -Logger $Logger
  $pluginRoot = Join-Path $repoRoot "plugins\devkit"
  $scriptsRoot = Join-Path $pluginRoot "scripts"
  $templateRoot = Join-Path $pluginRoot "templates\codex"
  $canSymlink = Test-DevKitSymlinkCapability

  Ensure-DevKitDir $codexRoot
  Ensure-DevKitDir $codexBin
  Ensure-DevKitDir $localBin
  Ensure-DevKitDir $codexDevKit
  Ensure-DevKitDir $codexDevKitTemplates
  Ensure-DevKitDirectoryContainer -Path $codexSkills

  foreach ($skill in (Get-DevKitSkillManifest)) {
    Ensure-DevKitLinkedDirectory `
      -SourcePath (Join-Path (Join-Path $pluginRoot "skills") $skill) `
      -DestinationPath (Join-Path $codexSkills $skill) `
      -CanSymlink $canSymlink `
      -ExpectedLegacyTarget (Join-Path (Join-Path $UserHome ".agent\skills") $skill)
  }

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
    Ensure-DevKitManagedFile `
      -SourcePath (Join-Path $scriptsRoot $fileName) `
      -DestinationPath (Join-Path $codexBin $fileName) `
      -AllowDifferentExistingContent
  }

  foreach ($fileName in @("config.shared.toml", "config.windows.toml")) {
    Ensure-DevKitManagedFile `
      -SourcePath (Join-Path $templateRoot $fileName) `
      -DestinationPath (Join-Path $codexDevKitTemplates $fileName) `
      -AllowDifferentExistingContent
  }

  Install-DevKitCommandShim -ShimPath (Join-Path $localBin "update-ccx.cmd") -TargetCommandPath (Join-Path $codexBin "update-ccx.cmd")
  Install-DevKitCommandShim -ShimPath (Join-Path $localBin "update-devkit.cmd") -TargetCommandPath (Join-Path $codexBin "update-devkit.cmd")
  Install-DevKitShellShim -ShimPath (Join-Path $localBin "update-ccx") -TargetScriptPath (Join-Path $codexBin "update-ccx.sh")
  Install-DevKitShellShim -ShimPath (Join-Path $localBin "update-devkit") -TargetScriptPath (Join-Path $codexBin "update-devkit.sh")
  [void](Ensure-DevKitUserPathContains -PathEntry $localBin)

  Write-DevKitUtf8NoBom -Path $codexSourceRootFile -Content ($repoRoot + "`n")

  $configResult = $null
  if ($RefreshConfig) {
    . (Join-Path $codexBin "devkit-codex-config.ps1")
    $configResult = Install-DevKitCodexConfig -UserHome $UserHome -OsName "windows"
  }

  return [pscustomobject]@{
    Runtime = "codex"
    SourceRoot = $repoRoot
    ConfigResult = $configResult
  }
}

function Sync-DevKitOpenCodeRuntime([string]$UserHome, [scriptblock]$Logger) {
  $opencodeRoot = Join-Path $UserHome ".config\opencode"
  $opencodeSkills = Join-Path $opencodeRoot "skills"
  $opencodeCommands = Join-Path $opencodeRoot "commands"
  $opencodeDevKit = Join-Path $opencodeRoot "devkit"
  $opencodeSourceRoot = Join-Path $opencodeDevKit "source"
  $opencodeSourceRootFile = Join-Path $opencodeDevKit "source-root.txt"
  $repoRoot = Ensure-DevKitSourceCheckout -SourceRoot $opencodeSourceRoot -Logger $Logger
  $pluginRoot = Join-Path $repoRoot "plugins\devkit"
  $canSymlink = Test-DevKitSymlinkCapability

  Ensure-DevKitDir $opencodeRoot
  Ensure-DevKitDir $opencodeDevKit
  Ensure-DevKitDirectoryContainer `
    -Path $opencodeSkills `
    -ExpectedLegacyTarget (Join-Path $UserHome ".agent\skills") `
    -AssertLegacySkillRoot
  Ensure-DevKitDirectoryContainer -Path $opencodeCommands

  foreach ($skill in (Get-DevKitSkillManifest)) {
    Ensure-DevKitLinkedDirectory `
      -SourcePath (Join-Path (Join-Path $pluginRoot "skills") $skill) `
      -DestinationPath (Join-Path $opencodeSkills $skill) `
      -CanSymlink $canSymlink `
      -ExpectedLegacyTarget (Join-Path (Join-Path $UserHome ".agent\skills") $skill)
  }

  Ensure-DevKitManagedFile `
    -SourcePath (Join-Path $pluginRoot "templates\opencode\commands\dig.md") `
    -DestinationPath (Join-Path $opencodeCommands "dig.md")

  Write-DevKitUtf8NoBom -Path $opencodeSourceRootFile -Content ($repoRoot + "`n")

  return [pscustomobject]@{
    Runtime = "opencode"
    SourceRoot = $repoRoot
  }
}
