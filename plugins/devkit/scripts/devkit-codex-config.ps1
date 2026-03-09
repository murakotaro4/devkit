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

function Get-DevKitCodexConfigPaths([string]$UserHome) {
  $codexRoot = Join-Path $UserHome ".codex"
  $devkitRoot = Join-Path $codexRoot "devkit"
  $templateRoot = Join-Path $devkitRoot "templates\codex"

  return [pscustomobject]@{
    CodexRoot = $codexRoot
    TemplateRoot = $templateRoot
    SharedTemplatePath = Join-Path $templateRoot "config.shared.toml"
    WindowsTemplatePath = Join-Path $templateRoot "config.windows.toml"
    LocalOverlayPath = Join-Path $codexRoot "config.local.toml"
    TargetPath = Join-Path $codexRoot "config.toml"
    BackupDir = Join-Path (Join-Path $codexRoot "logs") "backups"
  }
}

function Get-DevKitOsTemplatePath([pscustomobject]$Paths, [string]$OsName) {
  if ($OsName -eq "windows") {
    return $Paths.WindowsTemplatePath
  }

  throw "UNSUPPORTED_OS_TEMPLATE: $OsName"
}

function Assert-ValidDevKitLocalOverlay([string]$OverlayPath, [string]$Content) {
  if ([string]::IsNullOrWhiteSpace($Content)) {
    return
  }

  $currentSection = $null
  $lineNumber = 0
  $seenSections = New-Object 'System.Collections.Generic.HashSet[string]'
  $seenKeys = @{}

  foreach ($rawLine in ($Content -split "`r?`n")) {
    $lineNumber++
    $trimmed = $rawLine.Trim()

    if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) {
      continue
    }

    if ($trimmed -match '^\[(?<section>[^\]]+)\]\s*(?:#.*)?$') {
      $section = $matches.section
      if ($section -notmatch '^projects\.(?:''[^'']+''|"[^"]+")$') {
        throw "LOCAL_CONFIG_SECTION_NOT_ALLOWED: ${OverlayPath}:$lineNumber => [$section]"
      }
      if (-not $seenSections.Add($section)) {
        throw "LOCAL_CONFIG_DUPLICATE_SECTION: ${OverlayPath}:$lineNumber => [$section]"
      }
      $currentSection = $section
      $seenKeys[$currentSection] = New-Object 'System.Collections.Generic.HashSet[string]'
      continue
    }

    if ($trimmed -match '^(?<key>[A-Za-z0-9_]+)\s*=') {
      $key = $matches.key

      if ($null -eq $currentSection) {
        throw "LOCAL_CONFIG_TOP_LEVEL_KEY_NOT_ALLOWED: ${OverlayPath}:$lineNumber => $key"
      }

      if ($key -ne "trust_level") {
        throw "LOCAL_CONFIG_KEY_NOT_ALLOWED: ${OverlayPath}:$lineNumber => $key"
      }

      if (-not $seenKeys[$currentSection].Add($key)) {
        throw "LOCAL_CONFIG_DUPLICATE_KEY: ${OverlayPath}:$lineNumber => [$currentSection].$key"
      }
      continue
    }

    throw "LOCAL_CONFIG_INVALID_LINE: ${OverlayPath}:$lineNumber => $trimmed"
  }
}

function Get-DevKitBootstrapOverlayContent([string]$ConfigContent) {
  $currentSection = $null
  $orderedSections = New-Object System.Collections.Generic.List[string]
  $sectionValues = @{}

  foreach ($rawLine in ($ConfigContent -split "`r?`n")) {
    $trimmed = $rawLine.Trim()

    if ($trimmed.Length -eq 0 -or $trimmed.StartsWith("#")) {
      continue
    }

    if ($trimmed -match '^\[(?<section>[^\]]+)\]\s*(?:#.*)?$') {
      $section = $matches.section
      if ($section -match '^projects\.(?:''[^'']+''|"[^"]+")$') {
        if (-not $sectionValues.ContainsKey($section)) {
          $orderedSections.Add($section) | Out-Null
        }
        $sectionValues[$section] = $null
        $currentSection = $section
      } else {
        $currentSection = $null
      }
      continue
    }

    if ($null -ne $currentSection -and $trimmed -match '^trust_level\s*=') {
      $sectionValues[$currentSection] = $trimmed
    }
  }

  $fragments = @()
  foreach ($section in $orderedSections) {
    $trustLevelLine = $sectionValues[$section]
    if ([string]::IsNullOrWhiteSpace($trustLevelLine)) {
      continue
    }
    $fragments += "[{0}]`n{1}" -f $section, $trustLevelLine
  }

  if ($fragments.Count -eq 0) {
    return ""
  }

  return "# Bootstrapped by DevKit from the previous ~/.codex/config.toml.`n" + (($fragments -join "`n`n") + "`n")
}

function Ensure-DevKitLocalOverlay([string]$TargetPath, [string]$LocalOverlayPath) {
  if (Test-Path -LiteralPath $LocalOverlayPath) {
    return $false
  }
  if (-not (Test-Path -LiteralPath $TargetPath)) {
    return $false
  }

  $existingConfig = Read-DevKitTextFile -Path $TargetPath
  $bootstrapContent = Get-DevKitBootstrapOverlayContent -ConfigContent $existingConfig
  if ([string]::IsNullOrWhiteSpace($bootstrapContent)) {
    return $false
  }

  Write-DevKitUtf8NoBom -Path $LocalOverlayPath -Content $bootstrapContent
  return $true
}

function Join-DevKitTomlFragments([string[]]$Fragments) {
  $normalized = @()
  foreach ($fragment in $Fragments) {
    if ([string]::IsNullOrWhiteSpace($fragment)) {
      continue
    }
    $normalized += $fragment.Trim()
  }

  if ($normalized.Count -eq 0) {
    throw "EMPTY_CONFIG_FRAGMENTS"
  }

  return (($normalized -join "`n`n") + "`n")
}

function Get-DevKitCodexConfigContent([string]$SharedTemplatePath, [string]$OsTemplatePath, [string]$LocalOverlayPath) {
  $sharedContent = Read-DevKitTextFile -Path $SharedTemplatePath
  $osContent = Read-DevKitTextFile -Path $OsTemplatePath
  $overlayContent = ""

  if (Test-Path -LiteralPath $LocalOverlayPath) {
    $overlayContent = Read-DevKitTextFile -Path $LocalOverlayPath
    Assert-ValidDevKitLocalOverlay -OverlayPath $LocalOverlayPath -Content $overlayContent
  }

  return Join-DevKitTomlFragments -Fragments @($sharedContent, $osContent, $overlayContent)
}

function Backup-DevKitCodexConfig([string]$TargetPath, [string]$BackupDir) {
  if (-not (Test-Path -LiteralPath $TargetPath)) {
    return $null
  }

  Ensure-DevKitDir -Path $BackupDir
  $backupPath = Join-Path $BackupDir ("config-" + (Get-Date -Format "yyyyMMdd-HHmmss") + ".toml")
  Copy-Item -LiteralPath $TargetPath -Destination $backupPath -Force
  return $backupPath
}

function Restore-DevKitCodexConfig([string]$BackupPath, [string]$TargetPath) {
  if ([string]::IsNullOrWhiteSpace($BackupPath)) {
    return
  }

  if (-not (Test-Path -LiteralPath $BackupPath)) {
    throw "MISSING_CONFIG_BACKUP: $BackupPath"
  }

  Copy-Item -LiteralPath $BackupPath -Destination $TargetPath -Force
}

function Install-DevKitCodexConfig([string]$UserHome, [string]$OsName = "windows") {
  $paths = Get-DevKitCodexConfigPaths -UserHome $UserHome
  Ensure-DevKitDir -Path $paths.CodexRoot
  Ensure-DevKitDir -Path $paths.BackupDir

  $bootstrappedOverlay = Ensure-DevKitLocalOverlay -TargetPath $paths.TargetPath -LocalOverlayPath $paths.LocalOverlayPath
  $osTemplatePath = Get-DevKitOsTemplatePath -Paths $paths -OsName $OsName
  $content = Get-DevKitCodexConfigContent `
    -SharedTemplatePath $paths.SharedTemplatePath `
    -OsTemplatePath $osTemplatePath `
    -LocalOverlayPath $paths.LocalOverlayPath

  $backupPath = Backup-DevKitCodexConfig -TargetPath $paths.TargetPath -BackupDir $paths.BackupDir
  $tempPath = Join-Path $paths.CodexRoot ("config.toml.tmp." + [guid]::NewGuid().ToString("N"))
  $overlayUsed = (Test-Path -LiteralPath $paths.LocalOverlayPath) -and -not [string]::IsNullOrWhiteSpace((Get-Content -LiteralPath $paths.LocalOverlayPath -Raw -Encoding UTF8))

  try {
    Write-DevKitUtf8NoBom -Path $tempPath -Content $content
    Copy-Item -LiteralPath $tempPath -Destination $paths.TargetPath -Force
  } catch {
    if ($backupPath) {
      Restore-DevKitCodexConfig -BackupPath $backupPath -TargetPath $paths.TargetPath
    } elseif (Test-Path -LiteralPath $paths.TargetPath) {
      Remove-Item -LiteralPath $paths.TargetPath -Force -ErrorAction SilentlyContinue
    }
    throw
  } finally {
    if (Test-Path -LiteralPath $tempPath) {
      Remove-Item -LiteralPath $tempPath -Force -ErrorAction SilentlyContinue
    }
  }

  return [pscustomobject]@{
    TargetPath = $paths.TargetPath
    BackupPath = $backupPath
    LocalOverlayPath = $paths.LocalOverlayPath
    UsedLocalOverlay = $overlayUsed
    BootstrappedLocalOverlay = $bootstrappedOverlay
    OsTemplatePath = $osTemplatePath
  }
}
