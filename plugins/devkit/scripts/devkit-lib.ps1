function Get-DevKitRepoUrl {
  if (-not [string]::IsNullOrWhiteSpace($env:DEVKIT_REPO_URL)) {
    return $env:DEVKIT_REPO_URL.Trim()
  }

  return "https://github.com/murakotaro4/devkit.git"
}

function Get-DevKitManagedSkillEntries {
  return @(
    "dig",
    "improve-skill",
    "computer-use-chatgpt-pro",
    "gpt-pro",
    "deep-research",
    "codex-search",
    "discord-ops",
    "discord-rust-server-ops",
    "repo-maintainer",
    "repo-maintainer-init",
    "amazon-search",
    "mermaid-show",
    "dig-core",
    "dig-claude",
    "dig-codex",
    "dig-cursor",
    "dig-opencode",
    "codex-impl",
    "decomposition",
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

function Test-DevKitPathPresent([string]$Path) {
  try {
    return $null -ne (Get-Item -LiteralPath $Path -Force -ErrorAction Stop)
  } catch [System.Management.Automation.ItemNotFoundException] {
    return $false
  }
}

function Remove-DevKitPathOrThrow([string]$Path, [switch]$Recurse) {
  if (-not (Test-DevKitPathPresent -Path $Path)) {
    return
  }

  Remove-Item -LiteralPath $Path -Force -Recurse:$Recurse -ErrorAction SilentlyContinue
  if (Test-DevKitPathPresent -Path $Path) {
    throw "PRUNE_FAILED: $Path"
  }
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
  if (-not (Test-DevKitPathPresent -Path $Path)) {
    return $false
  }

  $item = Get-Item -LiteralPath $Path -Force -ErrorAction Stop
  return [bool]($item.Attributes -band [IO.FileAttributes]::ReparsePoint)
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

function Get-DevKitSourceRootStateFiles([string]$UserHome) {
  return @(
    (Join-Path (Join-Path $UserHome ".codex\devkit") "source-root.txt")
  )
}

function Get-DevKitPersistedSourceRoot([string]$UserHome) {
  foreach ($stateFile in (Get-DevKitSourceRootStateFiles -UserHome $UserHome)) {
    if (-not (Test-Path -LiteralPath $stateFile)) {
      continue
    }

    $candidate = (Get-Content -LiteralPath $stateFile -TotalCount 1 -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ([string]::IsNullOrWhiteSpace($candidate)) {
      continue
    }

    $repoRoot = Resolve-DevKitRepoRootFromHint $candidate.Trim()
    if (-not [string]::IsNullOrWhiteSpace($repoRoot)) {
      return $repoRoot
    }
  }

  return $null
}

function Set-DevKitPersistedSourceRoot([string]$StateFile, [string]$RepoRoot) {
  Ensure-DevKitDir (Split-Path -Parent $StateFile)
  Write-DevKitUtf8NoBom -Path $StateFile -Content ($RepoRoot.Trim() + "`n")
}

function Get-DevKitDefaultSourceRoot([string]$UserHome) {
  if (-not [string]::IsNullOrWhiteSpace($env:DEVKIT_SOURCE_ROOT)) {
    return $env:DEVKIT_SOURCE_ROOT.Trim()
  }

  $persisted = Get-DevKitPersistedSourceRoot -UserHome $UserHome
  if (-not [string]::IsNullOrWhiteSpace($persisted)) {
    return $persisted
  }

  return (Join-Path $UserHome "cursor\devkit")
}

function Resolve-DevKitRepoRootFromHint([string]$Hint) {
  if ([string]::IsNullOrWhiteSpace($Hint)) {
    return $null
  }

  $fullHint = Convert-DevKitToFullPath $Hint
  if ([string]::IsNullOrWhiteSpace($fullHint)) {
    return $null
  }

  if (Test-Path -LiteralPath (Join-Path $fullHint "plugins\devkit")) {
    return [IO.Path]::GetFullPath($Hint)
  }

  $pluginLike = @("skills", "scripts", "templates") | ForEach-Object { Join-Path $fullHint $_ }
  if (($pluginLike | Where-Object { Test-Path -LiteralPath $_ }).Count -eq 3) {
    return [IO.Path]::GetFullPath((Join-Path $Hint "..\.."))
  }

  return $null
}

function Get-DevKitScriptCheckoutRoot {
  if ([string]::IsNullOrWhiteSpace($PSScriptRoot)) {
    return $null
  }

  $candidate = Resolve-DevKitRepoRootFromHint (Join-Path $PSScriptRoot "..\..\..")
  if ([string]::IsNullOrWhiteSpace($candidate)) {
    return $null
  }

  if (-not (Test-Path -LiteralPath (Join-Path $candidate ".git"))) {
    return $null
  }

  return $candidate
}

function Get-DevKitRepoRoot([string]$UserHome, [scriptblock]$Logger) {
  $preferredRoot = Get-DevKitDefaultSourceRoot -UserHome $UserHome
  if (-not [string]::IsNullOrWhiteSpace($env:DEVKIT_SOURCE_ROOT)) {
    $repoRoot = Resolve-DevKitRepoRootFromHint $preferredRoot
  } else {
    $repoRoot = Get-DevKitScriptCheckoutRoot
    if ([string]::IsNullOrWhiteSpace($repoRoot)) {
      $repoRoot = Resolve-DevKitRepoRootFromHint $preferredRoot
    }
  }

  if ([string]::IsNullOrWhiteSpace($repoRoot)) {
    if (Test-Path -LiteralPath $preferredRoot) {
      $existingChildren = @(Get-ChildItem -LiteralPath $preferredRoot -Force -ErrorAction SilentlyContinue)
      if ($existingChildren.Count -gt 0) {
        throw "DEVKIT_SOURCE_ROOT_NOT_EMPTY: $preferredRoot"
      }
    } else {
      Ensure-DevKitDir (Split-Path -Parent $preferredRoot)
    }

    if (Test-DevKitCommandAvailable "git") {
      $repoUrl = Get-DevKitRepoUrl
      Invoke-DevKitLogger $Logger ("Cloning DevKit checkout: " + $preferredRoot)
      try {
        Invoke-DevKitGit -WorkingDirectory $null -Arguments @("clone", "--depth", "1", $repoUrl, $preferredRoot)
        $repoRoot = Resolve-DevKitRepoRootFromHint $preferredRoot
      } catch {
        if (Test-Path -LiteralPath $preferredRoot) {
          Remove-Item -LiteralPath $preferredRoot -Recurse -Force -ErrorAction SilentlyContinue
        }
        throw "DEVKIT_REPO_CLONE_FAILED: $preferredRoot"
      }
    }
  }

  if ([string]::IsNullOrWhiteSpace($repoRoot)) {
    throw "DEVKIT_REPO_ROOT_NOT_FOUND: expected DevKit under $preferredRoot"
  }

  $gitDir = Join-Path $repoRoot ".git"
  if (Test-Path -LiteralPath $gitDir) {
    if (-not (Test-DevKitCommandAvailable "git")) {
      Invoke-DevKitLogger $Logger "git is unavailable. Reusing the existing DevKit checkout."
    } else {
      & git -C $repoRoot symbolic-ref -q HEAD | Out-Null
      $symbolicRefExitCode = $LASTEXITCODE
      if ($symbolicRefExitCode -eq 0) {
        Invoke-DevKitLogger $Logger ("Updating DevKit checkout: " + $repoRoot)
        Invoke-DevKitGit -WorkingDirectory $repoRoot -Arguments @("pull", "--ff-only")
      } elseif ($symbolicRefExitCode -eq 1) {
        Invoke-DevKitLogger $Logger "Detached HEAD checkout. Reusing the existing DevKit checkout."
      } else {
        throw "DEVKIT_REPO_PULL_FAILED: $repoRoot"
      }
    }
  } elseif (-not (Test-Path -LiteralPath (Join-Path $repoRoot "plugins\devkit"))) {
    throw "DEVKIT_PLUGIN_ROOT_NOT_FOUND: $(Join-Path $repoRoot 'plugins\devkit')"
  }

  return $repoRoot
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

function Install-DevKitManagedFiles([string]$RepoRoot, [string]$UserHome) {
  $codexRoot = Join-Path $UserHome ".codex"
  $codexBin = Join-Path $codexRoot "bin"
  $localBin = Join-Path $UserHome ".local\bin"
  $codexDevKit = Join-Path $codexRoot "devkit"
  $codexDevKitTemplates = Join-Path $codexDevKit "templates\codex"
  $pluginRoot = Join-Path $RepoRoot "plugins\devkit"
  $scriptsRoot = Join-Path $pluginRoot "scripts"
  $templateRoot = Join-Path $pluginRoot "templates\codex"

  Ensure-DevKitDir $codexRoot
  Ensure-DevKitDir $codexBin
  Ensure-DevKitDir $localBin
  Ensure-DevKitDir $codexDevKit
  Ensure-DevKitDir $codexDevKitTemplates

  foreach ($fileName in @(
    "update-ccx.sh",
    "devkit-lib.sh",
    "update-ccx.cmd",
    "devkit-lib.ps1",
    "devkit-setup.ps1",
    "devkit-codex-config.ps1"
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

  Set-DevKitPersistedSourceRoot -StateFile (Join-Path $codexDevKit "source-root.txt") -RepoRoot $RepoRoot

  Install-DevKitCommandShim -ShimPath (Join-Path $localBin "update-ccx.cmd") -TargetCommandPath (Join-Path $codexBin "update-ccx.cmd")
  $legacyUpdaterPaths = @(
    (Join-Path $codexBin "update-devkit.sh"),
    (Join-Path $codexBin "update-devkit.ps1"),
    (Join-Path $codexBin "update-devkit.cmd"),
    (Join-Path $localBin "update-devkit"),
    (Join-Path $localBin "update-devkit.cmd")
  )
  foreach ($legacyPath in $legacyUpdaterPaths) {
    Remove-DevKitPathOrThrow -Path $legacyPath
  }
  [void](Ensure-DevKitUserPathContains -PathEntry $localBin)

  return [pscustomobject]@{
    CodexBin = $codexBin
    LocalBin = $localBin
    CodexDevKit = $codexDevKit
  }
}

function Test-DevKitPathLooksManaged([string]$Path) {
  $normalized = Convert-DevKitToFullPath $Path
  if ([string]::IsNullOrWhiteSpace($normalized)) {
    return $false
  }

  $codexPluginCacheRoot = "\.codex\plugins\cache\murakotaro4\devkit"
  return (
    $normalized.Contains("\plugins\devkit\skills") -or
    $normalized.EndsWith($codexPluginCacheRoot) -or
    $normalized.Contains($codexPluginCacheRoot + "\") -or
    $normalized.Contains("\.codex\devkit\source\") -or
    $normalized.Contains("\.claude\plugins\marketplaces\murakotaro4\") -or
    $normalized.Contains("\.config\opencode\devkit\")
  )
}

function Remove-DevKitManagedSkillLinks([string]$SkillsRoot) {
  if (-not (Test-Path -LiteralPath $SkillsRoot)) {
    return
  }

  if (Test-DevKitReparsePoint $SkillsRoot) {
    $target = Get-DevKitLinkTargetPath $SkillsRoot
    if (Test-DevKitPathLooksManaged $target) {
      Remove-DevKitPathOrThrow -Path $SkillsRoot -Recurse
      Ensure-DevKitDir $SkillsRoot
    }
    return
  }

  $managed = [System.Collections.Generic.HashSet[string]]::new([StringComparer]::OrdinalIgnoreCase)
  foreach ($skill in (Get-DevKitManagedSkillEntries)) {
    [void]$managed.Add($skill)
  }

  foreach ($entry in (Get-ChildItem -LiteralPath $SkillsRoot -Force -ErrorAction Stop)) {
    if (-not $managed.Contains($entry.Name)) {
      continue
    }
    if (-not (Test-DevKitReparsePoint $entry.FullName)) {
      continue
    }

    $target = Get-DevKitLinkTargetPath $entry.FullName
    if (Test-DevKitPathLooksManaged $target) {
      Remove-DevKitPathOrThrow -Path $entry.FullName -Recurse
    }
  }
}

function Remove-DevKitLegacyCommandFile([string]$Path) {
  if (-not (Test-Path -LiteralPath $Path)) {
    return
  }

  $content = Get-Content -LiteralPath $Path -Raw -ErrorAction Stop
  if ($content -and $content.Contains("runtime=opencode")) {
    Remove-DevKitPathOrThrow -Path $Path
  }
}

function Test-DevKitV9RetiredSkillEntryManaged([string]$Path, [string]$RetiredName) {
  try {
    if (Test-DevKitReparsePoint $Path) {
      $target = Get-DevKitLinkTargetPath $Path
      return (Test-DevKitPathLooksManaged $target)
    }

    if (-not (Test-Path -LiteralPath $Path -PathType Container)) {
      return $false
    }

    $skillFile = Join-Path $Path "SKILL.md"
    if (-not (Test-Path -LiteralPath $skillFile -PathType Leaf)) {
      return $false
    }

    $content = Read-DevKitTextFile -Path $skillFile
    $lines = @($content -split "\r?\n")
    if ($lines.Count -eq 0 -or $lines[0] -ne "---") {
      return $false
    }

    $frontmatterClosed = $false
    $frontmatterEndIndex = -1
    $nameCount = 0
    $nameMatches = $false
    for ($index = 1; $index -lt $lines.Count; $index++) {
      $line = $lines[$index]
      if ($line -eq "---") {
        $frontmatterClosed = $true
        $frontmatterEndIndex = $index
        break
      }
      if ($line -match '^\s*name\s*:') {
        $nameCount++
        if ($line -match '^\s*name\s*:\s*(?:"(?<value>[^"]+)"|''(?<value>[^'']+)''|(?<value>[^\s#]+))\s*$') {
          $nameMatches = [string]::Equals($Matches["value"], $RetiredName, [StringComparison]::Ordinal)
        } else {
          $nameMatches = $false
        }
      }
    }

    $bodyMarkerFound = $false
    if ($frontmatterClosed) {
      for ($bodyIndex = $frontmatterEndIndex + 1; $bodyIndex -lt $lines.Count; $bodyIndex++) {
        if ($lines[$bodyIndex].Contains('devkit リポジトリの `AGENTS.md`')) {
          $bodyMarkerFound = $true
          break
        }
      }
    }

    return (
      $frontmatterClosed -and
      $nameCount -eq 1 -and
      $nameMatches -and
      $bodyMarkerFound
    )
  } catch {
    return $false
  }
}

function Remove-DevKitV9RetiredSkillDirs([string]$UserHome) {
  foreach ($skillsRoot in @(
    (Join-Path $UserHome ".agents\skills"),
    (Join-Path $UserHome ".codex\skills"),
    (Join-Path $UserHome ".agent\skills"),
    (Join-Path $UserHome ".config\opencode\skills")
  )) {
    foreach ($retiredName in @("dig", "goal-prompt")) {
      $retiredEntry = Join-Path $skillsRoot $retiredName
      if (Test-DevKitV9RetiredSkillEntryManaged -Path $retiredEntry -RetiredName $retiredName) {
        Remove-DevKitPathOrThrow -Path $retiredEntry -Recurse
      }
    }
  }
}

function Remove-DevKitLegacyScheduledTask {
  if (-not (Get-Command Get-ScheduledTask -ErrorAction SilentlyContinue)) {
    return
  }

  $task = Get-ScheduledTask -TaskName "DevKitSkillsDailyUpdate" -ErrorAction SilentlyContinue
  if ($null -ne $task) {
    Unregister-ScheduledTask -TaskName "DevKitSkillsDailyUpdate" -Confirm:$false -ErrorAction SilentlyContinue
    if ($null -ne (Get-ScheduledTask -TaskName "DevKitSkillsDailyUpdate" -ErrorAction SilentlyContinue)) {
      throw "PRUNE_FAILED: scheduled task DevKitSkillsDailyUpdate"
    }
  }
}

function Clear-DevKitMarketplaceHooks([string]$UserHome) {
  if (-not (Test-DevKitCommandAvailable "git")) {
    return
  }

  $marketplaceRoot = Join-Path $UserHome ".claude\plugins\marketplaces\murakotaro4"
  if (-not (Test-Path -LiteralPath (Join-Path $marketplaceRoot ".git"))) {
    return
  }

  $hooksPath = & git -C $marketplaceRoot config --local --get core.hooksPath 2>$null
  if ($LASTEXITCODE -eq 0 -and $hooksPath -eq ".githooks") {
    & git -C $marketplaceRoot config --local --unset core.hooksPath 2>$null
  }
}

function Remove-DevKitLegacyAssets([string]$UserHome, [string]$SourceRoot, [scriptblock]$Logger) {
  $codexDevKit = Join-Path $UserHome ".codex\devkit"
  $markerPath = Join-Path $codexDevKit ".migrated-v6"
  $v9MarkerPath = Join-Path $codexDevKit ".migrated-v9-dig-goal"

  Ensure-DevKitDir $codexDevKit
  if (-not (Test-Path -LiteralPath $v9MarkerPath)) {
    Remove-DevKitV9RetiredSkillDirs -UserHome $UserHome
    Write-DevKitUtf8NoBom -Path $v9MarkerPath -Content "migrated-v9-dig-goal`n"
  }

  # v12 -> v13: update-ccx.ps1 の委譲シムを廃止したため、marker の有無に関わらず
  # 常時 prune する(v6 marker があると後続 cleanup は早期 return するため)。
  Remove-DevKitPathOrThrow -Path (Join-Path $UserHome ".codex\bin\update-ccx.ps1")

  if (Test-Path -LiteralPath $markerPath) {
    Invoke-DevKitLogger $Logger "Legacy migration marker already exists."
    return
  }

  foreach ($skillsRoot in @(
    (Join-Path $UserHome ".agents\skills"),
    (Join-Path $UserHome ".codex\skills"),
    (Join-Path $UserHome ".agent\skills"),
    (Join-Path $UserHome ".config\opencode\skills")
  )) {
    Remove-DevKitManagedSkillLinks -SkillsRoot $skillsRoot
  }

  Remove-DevKitLegacyCommandFile -Path (Join-Path $UserHome ".config\opencode\commands\dig.md")

  $legacyStateDir = Join-Path $UserHome ".config\opencode\devkit"
  if (Test-Path -LiteralPath $legacyStateDir) {
    Remove-DevKitPathOrThrow -Path $legacyStateDir -Recurse
  }

  if (-not [string]::IsNullOrWhiteSpace($SourceRoot)) {
    Set-DevKitPersistedSourceRoot -StateFile (Join-Path $codexDevKit "source-root.txt") -RepoRoot $SourceRoot
  }

  Clear-DevKitMarketplaceHooks -UserHome $UserHome

  $codexBin = Join-Path $UserHome ".codex\bin"
  $legacyCodexBinFileNames = @(
    "devkit-runtime-sync.ps1",
    "devkit-runtime-sync.sh",
    "devkit-skill-update.ps1",
    "devkit-skill-update.cmd",
    "update-devkit.sh",
    "update-devkit.ps1",
    "update-devkit.cmd"
  )
  foreach ($fileName in $legacyCodexBinFileNames) {
    $path = Join-Path $codexBin $fileName
    Remove-DevKitPathOrThrow -Path $path
  }

  $legacyLocalBinFileNames = @(
    "update-devkit",
    "update-devkit.cmd"
  )
  foreach ($fileName in $legacyLocalBinFileNames) {
    $path = Join-Path $UserHome ".local\bin\$fileName"
    Remove-DevKitPathOrThrow -Path $path
  }

  Remove-DevKitLegacyScheduledTask
  Write-DevKitUtf8NoBom -Path $markerPath -Content ("migrated_at=" + (Get-Date -Format "o") + "`n")
  Invoke-DevKitLogger $Logger "Legacy DevKit assets pruned."
}
