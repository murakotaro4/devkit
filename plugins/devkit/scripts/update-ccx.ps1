[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$CliArgs
)

$ErrorActionPreference = "Stop"

$Script:Errors = New-Object System.Collections.Generic.List[string]
$Script:Warnings = New-Object System.Collections.Generic.List[string]
$Script:ExpectedLegacyCodexPrefix = Join-Path $env:USERPROFILE ".npm-global"
$Script:CodexMigrationPerformed = $false
$Script:NpmRepairAttempted = $false
$Script:NpmUnavailableReported = $false
$Script:CliOnly = $false
$Script:DevKitOnly = $false

function Resolve-DevKitLibForUpdate {
  $libPath = Join-Path $PSScriptRoot "devkit-lib.ps1"
  if (Test-Path -LiteralPath $libPath) {
    $normalRoot = $null
    $checkoutCandidate = Join-Path $PSScriptRoot "..\..\..\plugins\devkit\scripts\devkit-lib.ps1"
    if (Test-Path -LiteralPath $checkoutCandidate) {
      $normalRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\.."))
    } elseif (Test-Path -LiteralPath (Join-Path $env:USERPROFILE "cursor\devkit\plugins\devkit\scripts\devkit-lib.ps1")) {
      $normalRoot = Join-Path $env:USERPROFILE "cursor\devkit"
    } else {
      $stateFile = Join-Path (Join-Path $env:USERPROFILE ".codex\devkit") "source-root.txt"
      if (Test-Path -LiteralPath $stateFile) {
        $normalRoot = (Get-Content -LiteralPath $stateFile -TotalCount 1 -ErrorAction SilentlyContinue | Select-Object -First 1)
        if ($null -ne $normalRoot) {
          $normalRoot = $normalRoot.Trim()
        }
      }
    }
    if ([string]::IsNullOrWhiteSpace($env:DEVKIT_SOURCE_ROOT) -and -not [string]::IsNullOrWhiteSpace($normalRoot)) {
      $env:DEVKIT_SOURCE_ROOT = $normalRoot
    }
    return $libPath
  }

  $repoCandidates = New-Object System.Collections.Generic.List[string]
  if (-not [string]::IsNullOrWhiteSpace($env:DEVKIT_SOURCE_ROOT)) {
    $repoCandidates.Add($env:DEVKIT_SOURCE_ROOT.Trim()) | Out-Null
  }
  $checkoutCandidate = Join-Path $PSScriptRoot "..\..\..\plugins\devkit\scripts\devkit-lib.ps1"
  if (Test-Path -LiteralPath $checkoutCandidate) {
    $repoCandidates.Add([IO.Path]::GetFullPath((Join-Path $PSScriptRoot "..\..\.."))) | Out-Null
  }
  $repoCandidates.Add((Join-Path $env:USERPROFILE "cursor\devkit")) | Out-Null

  $stateFile = Join-Path (Join-Path $env:USERPROFILE ".codex\devkit") "source-root.txt"
  if (Test-Path -LiteralPath $stateFile) {
    $repoRoot = (Get-Content -LiteralPath $stateFile -TotalCount 1 -ErrorAction SilentlyContinue | Select-Object -First 1)
    if ($null -ne $repoRoot) {
      $repoRoot = $repoRoot.Trim()
      if (-not [string]::IsNullOrWhiteSpace($repoRoot)) {
        $repoCandidates.Add($repoRoot) | Out-Null
      }
    }
  }

  foreach ($repoRoot in $repoCandidates) {
    if ([string]::IsNullOrWhiteSpace($repoRoot)) {
      continue
    }
    $repoLib = Join-Path $repoRoot "plugins\devkit\scripts\devkit-lib.ps1"
    if (Test-Path -LiteralPath $repoLib) {
      # v5 -> v6 one-time rebootstrap: old installed updaters do not know devkit-lib.ps1.
      $codexBin = Join-Path (Join-Path $env:USERPROFILE ".codex") "bin"
      New-Item -ItemType Directory -Path $codexBin -Force | Out-Null
      Copy-Item -LiteralPath $repoLib -Destination (Join-Path $codexBin "devkit-lib.ps1") -Force
      if ([string]::IsNullOrWhiteSpace($env:DEVKIT_SOURCE_ROOT)) {
        $env:DEVKIT_SOURCE_ROOT = $repoRoot
      }
      return (Join-Path $codexBin "devkit-lib.ps1")
    }
  }

  throw "MISSING_SOURCE_FILE: $libPath"
}

. (Resolve-DevKitLibForUpdate)

function Add-ResultError([string]$Message) {
  if (-not $Script:Errors.Contains($Message)) {
    $Script:Errors.Add($Message)
  }
}

function Add-ResultWarning([string]$Message) {
  if (-not $Script:Warnings.Contains($Message)) {
    $Script:Warnings.Add($Message)
  }
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Normalize-PathValue([string]$Path) {
  if ([string]::IsNullOrWhiteSpace($Path)) {
    return $null
  }
  return [IO.Path]::GetFullPath($Path).TrimEnd('\').ToLowerInvariant()
}

function Expand-PrefixValue([string]$Value) {
  if ([string]::IsNullOrWhiteSpace($Value)) {
    return $null
  }

  $expanded = [Environment]::ExpandEnvironmentVariables($Value.Trim().Trim('"').Trim("'"))
  if ($expanded.StartsWith('~\')) {
    $expanded = Join-Path $env:USERPROFILE $expanded.Substring(2)
  } elseif ($expanded -eq "~") {
    $expanded = $env:USERPROFILE
  }

  return Normalize-PathValue $expanded
}

function Test-CommandAvailable([string]$Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Get-CommandSource([string]$Name) {
  $command = Get-Command $Name -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($null -eq $command) {
    return $null
  }
  return $command.Source
}

function Invoke-Tool([string]$Command, [string[]]$Arguments, [switch]$CaptureOutput) {
  $output = & {
    param([string]$NativeCommand, [string[]]$NativeArguments)
    $ErrorActionPreference = "Continue"
    & $NativeCommand @NativeArguments 2>&1
  } $Command $Arguments

  return [pscustomobject]@{
    ExitCode = $LASTEXITCODE
    Output = @($output | ForEach-Object { $_.ToString() })
  }
}

function Get-WhereResults([string]$Name) {
  $output = & where.exe $Name 2>$null
  if ($LASTEXITCODE -ne 0) {
    return @()
  }
  return @($output | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Get-VersionFromSource([string]$Source) {
  if ([string]::IsNullOrWhiteSpace($Source)) {
    return $null
  }

  $result = Invoke-Tool -Command $Source -Arguments @("--version") -CaptureOutput
  if ($result.ExitCode -ne 0) {
    return $null
  }

  foreach ($line in $result.Output) {
    if ($line -match '([0-9]+\.[0-9]+\.[0-9]+(?:[-+.][0-9A-Za-z]+)*)') {
      return $Matches[1]
    }
  }

  return $null
}

function Get-VersionFromCommand([string]$Name) {
  $version = Get-VersionFromSource (Get-CommandSource $Name)
  if ([string]::IsNullOrWhiteSpace($version)) {
    return "unknown"
  }
  return $version
}

function Test-PathContains([string]$Path, [string[]]$Fragments) {
  $normalized = Normalize-PathValue $Path
  if ([string]::IsNullOrWhiteSpace($normalized)) {
    return $false
  }

  foreach ($fragment in $Fragments) {
    if ($normalized.Contains($fragment.ToLowerInvariant())) {
      return $true
    }
  }

  return $false
}

function Refresh-FnmEnvironment {
  if (-not (Test-CommandAvailable "fnm")) {
    return
  }

  $envLines = & fnm env --shell powershell 2>$null
  if ($LASTEXITCODE -ne 0) {
    return
  }

  foreach ($line in $envLines) {
    if (-not [string]::IsNullOrWhiteSpace($line)) {
      Invoke-Expression $line
    }
  }
}

function Get-ActiveFnmVersion {
  if (-not (Test-CommandAvailable "fnm")) {
    return $null
  }

  $current = (& fnm current 2>$null | Select-Object -First 1)
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($current)) {
    return $null
  }

  $current = $current.Trim()
  if ($current -eq "system") {
    return $null
  }

  if ($current -notmatch '^v') {
    $current = "v$current"
  }

  return $current
}

function Convert-ToVersionTag([string]$Version) {
  if ([string]::IsNullOrWhiteSpace($Version)) {
    return $null
  }

  $normalized = $Version.Trim()
  if ($normalized -eq "system") {
    return $null
  }

  if ($normalized -notmatch '^v') {
    $normalized = "v$normalized"
  }

  return $normalized
}

function Get-FnmDefaultInstallRoot {
  $aliasRoot = Join-Path $env:APPDATA "fnm\aliases\default"
  if (Test-Path -LiteralPath $aliasRoot) {
    return $aliasRoot
  }

  return $null
}

function Get-FnmVersionFromInstallRoot([string]$InstallRoot) {
  $normalized = Normalize-PathValue $InstallRoot
  if ([string]::IsNullOrWhiteSpace($normalized)) {
    return $null
  }

  if ($normalized -match '\\node-versions\\([^\\]+)\\installation$') {
    return Convert-ToVersionTag $Matches[1]
  }

  return $null
}

function Get-FnmDefaultVersion {
  $aliasRoot = Get-FnmDefaultInstallRoot
  if ([string]::IsNullOrWhiteSpace($aliasRoot)) {
    return $null
  }

  $aliasItem = Get-Item -LiteralPath $aliasRoot -Force -ErrorAction SilentlyContinue
  if ($null -ne $aliasItem) {
    $targets = @($aliasItem.Target)
    if ($targets.Count -gt 0) {
      $targetVersion = Get-FnmVersionFromInstallRoot $targets[0]
      if (-not [string]::IsNullOrWhiteSpace($targetVersion)) {
        return $targetVersion
      }
    }
  }

  return Get-FnmVersionFromInstallRoot $aliasRoot
}

function Get-FnmInstallRootForVersion([string]$Version) {
  $normalizedVersion = Convert-ToVersionTag $Version
  if ([string]::IsNullOrWhiteSpace($normalizedVersion)) {
    return $null
  }

  return Join-Path $env:APPDATA "fnm\node-versions\$normalizedVersion\installation"
}

function Get-FnmInstallRoot {
  $version = Get-ActiveFnmVersion
  if (-not [string]::IsNullOrWhiteSpace($version)) {
    $root = Get-FnmInstallRootForVersion $version
    if (Test-Path -LiteralPath $root) {
      return $root
    }
  }

  return Get-FnmDefaultInstallRoot
}

function Get-FnmVersionsWithNpm([string]$ExcludeVersion) {
  $versionsRoot = Join-Path $env:APPDATA "fnm\node-versions"
  if (-not (Test-Path -LiteralPath $versionsRoot)) {
    return @()
  }

  $excluded = Convert-ToVersionTag $ExcludeVersion
  $versions = New-Object System.Collections.Generic.List[string]
  foreach ($directory in Get-ChildItem -LiteralPath $versionsRoot -Directory -ErrorAction SilentlyContinue) {
    $version = Convert-ToVersionTag $directory.Name
    if ([string]::IsNullOrWhiteSpace($version) -or $version -eq $excluded) {
      continue
    }

    $npmCommand = Join-Path $directory.FullName "installation\npm.cmd"
    if (Test-Path -LiteralPath $npmCommand) {
      $versions.Add($version)
    }
  }

  return @($versions | Sort-Object -Unique)
}

function Ensure-PathStartsWith([string]$PathEntry, [switch]$PersistUserPath) {
  if ([string]::IsNullOrWhiteSpace($PathEntry)) {
    return
  }

  $target = Normalize-PathValue $PathEntry
  if ([string]::IsNullOrWhiteSpace($target)) {
    return
  }

  $sessionEntries = @($env:PATH -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
  $sessionEntries = @($sessionEntries | Where-Object { (Normalize-PathValue $_) -ne $target })
  $env:PATH = (@($PathEntry) + $sessionEntries) -join ';'

  if (-not $PersistUserPath) {
    return
  }

  $userEntries = @()
  $currentUserPath = [Environment]::GetEnvironmentVariable("Path", "User")
  if (-not [string]::IsNullOrWhiteSpace($currentUserPath)) {
    $userEntries = @($currentUserPath -split ';' | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $userEntries = @($userEntries | Where-Object { (Normalize-PathValue $_) -ne $target })
  }

  [Environment]::SetEnvironmentVariable("Path", ((@($PathEntry) + $userEntries) -join ';'), "User")
}

function Refresh-ProcessPathFromRegistry {
  $entries = New-Object System.Collections.Generic.List[string]
  $seen = New-Object System.Collections.Generic.HashSet[string]

  foreach ($pathScope in @("Machine", "User")) {
    $scopePath = [Environment]::GetEnvironmentVariable("Path", $pathScope)
    if ([string]::IsNullOrWhiteSpace($scopePath)) {
      continue
    }

    foreach ($entry in ($scopePath -split ';')) {
      if ([string]::IsNullOrWhiteSpace($entry)) {
        continue
      }
      $normalized = Normalize-PathValue $entry
      if ([string]::IsNullOrWhiteSpace($normalized) -or -not $seen.Add($normalized)) {
        continue
      }
      $entries.Add($entry)
    }
  }

  foreach ($entry in ($env:PATH -split ';')) {
    if ([string]::IsNullOrWhiteSpace($entry)) {
      continue
    }
    $normalized = Normalize-PathValue $entry
    if ([string]::IsNullOrWhiteSpace($normalized) -or -not $seen.Add($normalized)) {
      continue
    }
    $entries.Add($entry)
  }

  if ($entries.Count -gt 0) {
    $env:PATH = ($entries -join ';')
  }
}

function Get-PreferredNpmCommand {
  $currentNpm = Get-CommandSource "npm"
  if (-not [string]::IsNullOrWhiteSpace($currentNpm)) {
    if ($currentNpm.ToLowerInvariant().EndsWith(".ps1")) {
      $cmdSibling = [IO.Path]::ChangeExtension($currentNpm, ".cmd")
      if (Test-Path -LiteralPath $cmdSibling) {
        return $cmdSibling
      }
    }
    return $currentNpm
  }

  $fnmInstallRoot = Get-FnmInstallRoot
  if (-not [string]::IsNullOrWhiteSpace($fnmInstallRoot)) {
    $stableNpm = Join-Path $fnmInstallRoot "npm.cmd"
    if (Test-Path -LiteralPath $stableNpm) {
      return $stableNpm
    }
  }

  return $null
}

function Get-NodeToolchainState {
  $nodeCommand = Get-CommandSource "node"
  $nodeVersion = Get-VersionFromSource $nodeCommand
  $npmCommand = Get-PreferredNpmCommand
  $npmVersion = Get-VersionFromSource $npmCommand

  $activeFnmVersion = Get-ActiveFnmVersion
  $defaultFnmVersion = Get-FnmDefaultVersion
  $targetFnmVersion = if (-not [string]::IsNullOrWhiteSpace($activeFnmVersion)) { $activeFnmVersion } else { $defaultFnmVersion }

  $fnmInstallRoot = $null
  if (-not [string]::IsNullOrWhiteSpace($targetFnmVersion)) {
    $fnmInstallRoot = Get-FnmInstallRootForVersion $targetFnmVersion
  } else {
    $fnmInstallRoot = Get-FnmInstallRoot
  }

  $expectedNpmCommand = if (-not [string]::IsNullOrWhiteSpace($fnmInstallRoot)) {
    Join-Path $fnmInstallRoot "npm.cmd"
  } else {
    $null
  }

  $isFnmManagedNode = Test-PathContains -Path $nodeCommand -Fragments @("\appdata\roaming\fnm\", "\appdata\local\fnm_multishells\")
  if (-not $isFnmManagedNode -and -not [string]::IsNullOrWhiteSpace($fnmInstallRoot)) {
    $isFnmManagedNode = Test-PathContains -Path $fnmInstallRoot -Fragments @("\appdata\roaming\fnm\")
  }

  return [pscustomobject]@{
    NodeCommand = $nodeCommand
    NodeVersion = $nodeVersion
    NpmCommand = $npmCommand
    NpmVersion = $npmVersion
    NpmReady = (-not [string]::IsNullOrWhiteSpace($npmCommand) -and -not [string]::IsNullOrWhiteSpace($npmVersion))
    FnmActiveVersion = $activeFnmVersion
    FnmDefaultVersion = $defaultFnmVersion
    FnmTargetVersion = $targetFnmVersion
    FnmInstallRoot = $fnmInstallRoot
    ExpectedNpmCommand = $expectedNpmCommand
    IsFnmManagedNode = $isFnmManagedNode
    AlternativeNpmVersions = @(Get-FnmVersionsWithNpm -ExcludeVersion $targetFnmVersion)
    RepairAttempted = $Script:NpmRepairAttempted
  }
}

function Invoke-FnmInstallForVersion([string]$Version) {
  $normalizedVersion = Convert-ToVersionTag $Version
  if ([string]::IsNullOrWhiteSpace($normalizedVersion)) {
    return $false
  }

  $installResult = Invoke-Tool -Command "fnm" -Arguments @("install", $normalizedVersion)
  if ($installResult.ExitCode -ne 0) {
    return $false
  }

  $defaultResult = Invoke-Tool -Command "fnm" -Arguments @("default", $normalizedVersion)
  if ($defaultResult.ExitCode -ne 0) {
    return $false
  }

  Refresh-FnmEnvironment
  return $true
}

function Restore-FnmInstallBackup([string]$BackupPath, [string]$InstallRoot) {
  if (
    [string]::IsNullOrWhiteSpace($BackupPath) -or
    [string]::IsNullOrWhiteSpace($InstallRoot) -or
    -not (Test-Path -LiteralPath $BackupPath)
  ) {
    return $false
  }

  try {
    if (Test-Path -LiteralPath $InstallRoot) {
      Remove-Item -LiteralPath $InstallRoot -Recurse -Force
    }

    Move-Item -LiteralPath $BackupPath -Destination $InstallRoot
    Refresh-FnmEnvironment
    return $true
  } catch {
    return $false
  }
}

function Repair-NodeToolchain([psobject]$State) {
  if ($Script:NpmRepairAttempted) {
    $latestState = Get-NodeToolchainState
    $latestState.RepairAttempted = $true
    return $latestState
  }

  $Script:NpmRepairAttempted = $true
  if (
    -not (Test-CommandAvailable "fnm") -or
    [string]::IsNullOrWhiteSpace($State.FnmTargetVersion) -or
    [string]::IsNullOrWhiteSpace($State.FnmInstallRoot)
  ) {
    $latestState = Get-NodeToolchainState
    $latestState.RepairAttempted = $true
    return $latestState
  }

  Write-Host -NoNewline ("Repairing Node.js toolchain ({0})... " -f $State.FnmTargetVersion)

  $installRoot = $State.FnmInstallRoot
  $backupPath = $null

  if (Invoke-FnmInstallForVersion -Version $State.FnmTargetVersion) {
    $latestState = Get-NodeToolchainState
    $latestState.RepairAttempted = $true
    if ($latestState.NpmReady) {
      Write-Host "OK"
      return $latestState
    }
  }

  if (Test-Path -LiteralPath $installRoot) {
    $backupPath = "{0}.update-ccx-broken.{1}" -f $installRoot, (Get-Date -Format "yyyyMMddHHmmss")
    try {
      Move-Item -LiteralPath $installRoot -Destination $backupPath

      if (Invoke-FnmInstallForVersion -Version $State.FnmTargetVersion) {
        $latestState = Get-NodeToolchainState
        $latestState.RepairAttempted = $true
        if ($latestState.NpmReady) {
          Add-ResultWarning ("Node.js: preserved the previous broken fnm install at {0}" -f $backupPath)
          Write-Host "OK"
          return $latestState
        }
      }
    } catch {
      Add-ResultWarning ("Node.js: failed to preserve the broken fnm install before repair ({0})" -f $_.Exception.Message)
    }
  }

  if (-not [string]::IsNullOrWhiteSpace($backupPath)) {
    if (-not (Restore-FnmInstallBackup -BackupPath $backupPath -InstallRoot $installRoot)) {
      Add-ResultWarning ("Node.js: repair failed and left a backup at {0}" -f $backupPath)
    }
  } else {
    Refresh-FnmEnvironment
  }

  $latestState = Get-NodeToolchainState
  $latestState.RepairAttempted = $true
  Write-Host "FAILED"
  return $latestState
}

function Get-NpmUnavailableMessage([psobject]$State) {
  $nodeVersion = if ([string]::IsNullOrWhiteSpace($State.NodeVersion)) { "unknown" } else { $State.NodeVersion }
  $fnmVersion = if ([string]::IsNullOrWhiteSpace($State.FnmTargetVersion)) { $nodeVersion } else { $State.FnmTargetVersion }
  $targetLabel = if ($State.IsFnmManagedNode -or -not [string]::IsNullOrWhiteSpace($State.FnmTargetVersion)) {
    "fnm-managed Node $fnmVersion"
  } else {
    "Node.js $nodeVersion"
  }

  $details = New-Object System.Collections.Generic.List[string]
  if ($State.RepairAttempted) {
    $details.Add("update-ccx tried to repair it with fnm")
  }
  if (-not [string]::IsNullOrWhiteSpace($State.NodeCommand)) {
    $details.Add(("node={0}" -f $State.NodeCommand))
  }
  if (-not [string]::IsNullOrWhiteSpace($State.FnmInstallRoot)) {
    $details.Add(("install_root={0}" -f $State.FnmInstallRoot))
  }
  if (-not [string]::IsNullOrWhiteSpace($State.ExpectedNpmCommand)) {
    $details.Add(("expected_npm={0}" -f $State.ExpectedNpmCommand))
  }
  if ($State.AlternativeNpmVersions.Count -gt 0) {
    $details.Add(("other_npm_ready_versions={0}" -f ($State.AlternativeNpmVersions -join ", ")))
  }

  $detailText = if ($details.Count -gt 0) {
    " " + ($details -join " / ")
  } else {
    ""
  }

  return ("Node.js: npm is unavailable for {0}.{1}" -f $targetLabel, $detailText)
}

function Report-NpmUnavailable([psobject]$State) {
  if ($Script:NpmUnavailableReported) {
    return
  }

  $Script:NpmUnavailableReported = $true
  Add-ResultError (Get-NpmUnavailableMessage -State $State)
}

function Get-ReadyNpmRuntime([switch]$AttemptRepair, [switch]$ReportError) {
  $state = Get-NodeToolchainState
  if (-not $state.NpmReady -and $AttemptRepair) {
    $state = Repair-NodeToolchain -State $state
  }

  if (-not $state.NpmReady -and $ReportError) {
    Report-NpmUnavailable -State $state
  }

  return $state
}

function Get-NpmGlobalPrefix([string]$NpmCommand) {
  if ([string]::IsNullOrWhiteSpace($NpmCommand)) {
    return $null
  }

  $result = Invoke-Tool -Command $NpmCommand -Arguments @("config", "get", "prefix") -CaptureOutput
  if ($result.ExitCode -ne 0) {
    return $null
  }

  foreach ($line in $result.Output) {
    if (-not [string]::IsNullOrWhiteSpace($line)) {
      return $line.Trim()
    }
  }

  return $null
}

function Get-LegacyNpmrcState {
  $npmrcPath = Join-Path $env:USERPROFILE ".npmrc"
  if (-not (Test-Path -LiteralPath $npmrcPath)) {
    return [pscustomobject]@{
      Path = $npmrcPath
      Exists = $false
      Content = ""
      PrefixLines = @()
    }
  }

  $content = [IO.File]::ReadAllText($npmrcPath)
  $lines = if ($content.Length -eq 0) { @() } else { $content -split "`r?`n" }
  $prefixLines = @()

  for ($i = 0; $i -lt $lines.Count; $i++) {
    if ($lines[$i] -match '^\s*prefix\s*=\s*(.+?)\s*$') {
      $prefixLines += [pscustomobject]@{
        Index = $i
        Raw = $lines[$i]
        Value = $Matches[1]
      }
    }
  }

  return [pscustomobject]@{
    Path = $npmrcPath
    Exists = $true
    Content = $content
    Lines = $lines
    PrefixLines = $prefixLines
  }
}

function Remove-PrefixLines([string[]]$Lines) {
  if ($null -eq $Lines) {
    return ""
  }

  $filtered = @($Lines | Where-Object { $_ -notmatch '^\s*prefix\s*=' })
  if ($filtered.Count -eq 0) {
    return ""
  }

  return ($filtered -join "`r`n") + "`r`n"
}

function Get-CodexDuplicateWarning([string[]]$Candidates) {
  if ($Candidates.Count -le 1) {
    return $null
  }

  $roots = New-Object System.Collections.Generic.List[string]
  foreach ($candidate in $Candidates) {
    $fullPath = Normalize-PathValue $candidate
    if ([string]::IsNullOrWhiteSpace($fullPath)) {
      continue
    }

    if (
      $fullPath.Contains("\appdata\roaming\fnm\") -or
      $fullPath.Contains("\appdata\local\fnm_multishells\") -or
      $fullPath.Contains("\appdata\roaming\npm\") -or
      $fullPath.Contains("\.npm-global\")
    ) {
      if (-not $roots.Contains("npm-managed")) {
        $roots.Add("npm-managed")
      }
      continue
    }

    $directory = Normalize-PathValue ([IO.Path]::GetDirectoryName($fullPath))
    if (-not [string]::IsNullOrWhiteSpace($directory) -and -not $roots.Contains($directory)) {
      $roots.Add($directory)
    }
  }

  if ($roots.Count -le 1) {
    return $null
  }

  $joined = ($roots -join ", ")
  return "Codex CLI: multiple install roots found ($joined). Run where.exe codex and keep the npm-managed path ahead of any standalone codex.exe."
}

function Detect-ClaudeInstall {
  $source = Get-CommandSource "claude"
  if ([string]::IsNullOrWhiteSpace($source)) {
    return [pscustomobject]@{ Method = "not_found"; Source = $null }
  }

  if (Test-PathContains -Path $source -Fragments @("\.local\bin\claude.exe", "\.local\share\claude\")) {
    return [pscustomobject]@{ Method = "native"; Source = $source }
  }

  if (Test-PathContains -Path $source -Fragments @("\node_modules\", "\.npm\", "\.npm-global\", "\appdata\roaming\npm\", "\appdata\roaming\fnm\", "\appdata\local\fnm_multishells\")) {
    return [pscustomobject]@{ Method = "npm"; Source = $source }
  }

  $help = Invoke-Tool -Command $source -Arguments @("update", "--help")
  if ($help.ExitCode -eq 0) {
    return [pscustomobject]@{ Method = "native"; Source = $source }
  }

  return [pscustomobject]@{ Method = "npm"; Source = $source }
}

function Detect-CodexInstall {
  $source = Get-CommandSource "codex"
  $candidates = Get-WhereResults "codex"
  if ([string]::IsNullOrWhiteSpace($source)) {
    return [pscustomobject]@{ Method = "not_found"; Source = $null; Candidates = $candidates }
  }

  if (Test-PathContains -Path $source -Fragments @("\node_modules\", "\.npm\", "\.npm-global\", "\appdata\roaming\npm\", "\appdata\roaming\fnm\", "\appdata\local\fnm_multishells\")) {
    return [pscustomobject]@{ Method = "npm"; Source = $source; Candidates = $candidates }
  }

  return [pscustomobject]@{ Method = "external"; Source = $source; Candidates = $candidates }
}

function Show-Versions {
  Write-Host "Environment: windows"
  Write-Host ("Claude Code: {0}" -f (Get-VersionFromCommand "claude"))
  Write-Host ("Codex CLI:   {0}" -f (Get-VersionFromCommand "codex"))
}

function Section-Prerequisites {
  Write-Host ""
  Write-Host "=== [Prerequisites] ==="
  Write-Host ("OK: PowerShell {0}" -f $PSVersionTable.PSVersion)

  if (Test-CommandAvailable "winget") {
    Write-Host "OK: winget available"
  } else {
    Write-Host "WARN: winget not found (fnm install cannot be automated)"
  }
}

function Ensure-Fnm {
  if (Test-CommandAvailable "fnm") {
    $version = (& fnm --version 2>$null | Select-Object -First 1)
    Write-Host ("OK: fnm already installed ({0})" -f $version)
    Refresh-FnmEnvironment
    return
  }

  if (-not (Test-CommandAvailable "winget")) {
    Add-ResultError "fnm: winget not available, install fnm manually and re-run update-ccx.cmd."
    return
  }

  Write-Host -NoNewline "Installing fnm... "
  $result = Invoke-Tool -Command "winget" -Arguments @(
    "install",
    "Schniz.fnm",
    "--accept-package-agreements",
    "--accept-source-agreements"
  )

  if ($result.ExitCode -ne 0) {
    Write-Host "FAILED"
    Add-ResultError ("fnm: winget install failed (exit code {0})" -f $result.ExitCode)
    return
  }

  Refresh-ProcessPathFromRegistry
  Refresh-FnmEnvironment
  if (Test-CommandAvailable "fnm") {
    $version = (& fnm --version 2>$null | Select-Object -First 1)
    Write-Host ("OK ({0})" -f $version)
  } else {
    Write-Host "FAILED"
    Add-ResultError "fnm: install completed but fnm is still not on PATH."
  }
}

function Ensure-NodeJs {
  if (Test-CommandAvailable "node") {
    $runtime = Get-ReadyNpmRuntime -AttemptRepair -ReportError
    $versionLabel = if ([string]::IsNullOrWhiteSpace($runtime.NodeVersion)) { "unknown" } else { $runtime.NodeVersion }
    if ($runtime.NpmReady) {
      if ($runtime.RepairAttempted) {
        Write-Host ("OK: Node.js already installed ({0} / npm repaired)" -f $versionLabel)
      } else {
        Write-Host ("OK: Node.js already installed ({0} / npm {1})" -f $versionLabel, $runtime.NpmVersion)
      }
    } else {
      Write-Host ("FAILED: Node.js installation is missing npm ({0})" -f $versionLabel)
    }
    return
  }

  if (-not (Test-CommandAvailable "fnm")) {
    Add-ResultError "Node.js: fnm not available, cannot install Node.js."
    return
  }

  Write-Host -NoNewline "Installing Node.js (LTS)... "
  $installResult = Invoke-Tool -Command "fnm" -Arguments @("install", "--lts")
  if ($installResult.ExitCode -ne 0) {
    Write-Host "FAILED"
    Add-ResultError ("Node.js: fnm install --lts failed (exit code {0})" -f $installResult.ExitCode)
    return
  }

  $defaultResult = Invoke-Tool -Command "fnm" -Arguments @("default", "lts-latest")
  if ($defaultResult.ExitCode -ne 0) {
    Write-Host "FAILED"
    Add-ResultError ("Node.js: fnm default lts-latest failed (exit code {0})" -f $defaultResult.ExitCode)
    return
  }

  Refresh-FnmEnvironment
  $runtime = Get-ReadyNpmRuntime -AttemptRepair -ReportError
  if ((Test-CommandAvailable "node") -and $runtime.NpmReady) {
    $versionLabel = if ([string]::IsNullOrWhiteSpace($runtime.NodeVersion)) { "unknown" } else { $runtime.NodeVersion }
    Write-Host ("OK ({0} / npm {1})" -f $versionLabel, $runtime.NpmVersion)
  } else {
    Write-Host "FAILED"
    if (-not (Test-CommandAvailable "node")) {
      Add-ResultError "Node.js: fnm installed Node.js but node is still not on PATH."
    }
  }
}

function Ensure-Claude {
  if (Test-CommandAvailable "claude") {
    Write-Host ("OK: Claude Code already installed ({0})" -f (Get-VersionFromCommand "claude"))
    return
  }

  Write-Host -NoNewline "Installing Claude Code (native)... "
  try {
    $scriptBody = (Invoke-WebRequest -UseBasicParsing "https://claude.ai/install.ps1").Content
    Invoke-Expression $scriptBody
    $env:PATH = "$env:USERPROFILE\.local\bin;$env:PATH"
  } catch {
    Write-Host "FAILED"
    Add-ResultError ("Claude Code: native install failed ({0})" -f $_.Exception.Message)
    return
  }

  if (Test-CommandAvailable "claude") {
    Write-Host "OK"
  } else {
    Write-Host "FAILED"
    Add-ResultError "Claude Code: install completed but claude is still not on PATH."
  }
}

function Invoke-CodexMigrationIfNeeded {
  $npmrcState = Get-LegacyNpmrcState
  if (-not $npmrcState.Exists -or $npmrcState.PrefixLines.Count -eq 0) {
    return $true
  }

  $expectedPrefix = Normalize-PathValue $Script:ExpectedLegacyCodexPrefix
  foreach ($prefixLine in $npmrcState.PrefixLines) {
    $actualPrefix = Expand-PrefixValue $prefixLine.Value
    if ($actualPrefix -ne $expectedPrefix) {
      Add-ResultError ("Codex migration: unexpected npm prefix '{0}' found in {1}. Manual review required." -f $prefixLine.Value, $npmrcState.Path)
      return $false
    }
  }

  $npmRuntime = Get-ReadyNpmRuntime -AttemptRepair -ReportError
  $preferredNpm = $npmRuntime.NpmCommand
  if (-not $npmRuntime.NpmReady) {
    return $false
  }

  $backupPath = Join-Path $env:USERPROFILE (".npmrc.update-ccx.bak." + (Get-Date -Format "yyyyMMddHHmmss"))
  Copy-Item -LiteralPath $npmrcState.Path -Destination $backupPath -Force

  $currentNpm = Get-CommandSource "npm"
  Write-Host ("Migrating Codex from legacy prefix {0} to fnm-managed Node..." -f $Script:ExpectedLegacyCodexPrefix)

  if (-not [string]::IsNullOrWhiteSpace($currentNpm)) {
    $uninstall = Invoke-Tool -Command $currentNpm -Arguments @("uninstall", "-g", "@openai/codex") -CaptureOutput
    if ($uninstall.ExitCode -ne 0) {
      Add-ResultWarning ("Codex migration: uninstall from legacy prefix exited with {0}; continuing with reinstall." -f $uninstall.ExitCode)
    }
  }

  $updatedContent = Remove-PrefixLines -Lines $npmrcState.Lines
  try {
    Write-Utf8NoBom -Path $npmrcState.Path -Content $updatedContent
    $destinationPrefix = Get-NpmGlobalPrefix -NpmCommand $preferredNpm
    if ([string]::IsNullOrWhiteSpace($destinationPrefix)) {
      throw "npm config get prefix failed after removing the legacy prefix"
    }
    $install = Invoke-Tool -Command $preferredNpm -Arguments @("install", "-g", "@openai/codex") -CaptureOutput
    if ($install.ExitCode -ne 0) {
      throw ("npm install -g @openai/codex failed (exit code {0})" -f $install.ExitCode)
    }

    Refresh-FnmEnvironment
    Ensure-PathStartsWith -PathEntry $destinationPrefix -PersistUserPath
    $resolvedCodex = Get-CommandSource "codex"
    if ([string]::IsNullOrWhiteSpace($resolvedCodex)) {
      throw "codex is still not on PATH after migration"
    }

    $Script:CodexMigrationPerformed = $true
    Write-Host ("Codex migration complete. Backup: {0}" -f $backupPath)
    return $true
  } catch {
    Copy-Item -LiteralPath $backupPath -Destination $npmrcState.Path -Force
    Add-ResultError ("Codex migration failed: {0}" -f $_.Exception.Message)
    return $false
  }
}

function Ensure-Codex {
  if (-not (Invoke-CodexMigrationIfNeeded)) {
    return
  }

  $npmRuntime = Get-ReadyNpmRuntime -AttemptRepair -ReportError
  $npmCommand = $npmRuntime.NpmCommand
  $codexInfo = Detect-CodexInstall
  if ($codexInfo.Method -eq "npm") {
    Write-Host ("OK: Codex CLI already installed ({0})" -f (Get-VersionFromCommand "codex"))
    return
  }

  if (-not $npmRuntime.NpmReady) {
    return
  }

  if ($codexInfo.Method -eq "external") {
    $existingInstall = Invoke-Tool -Command $npmCommand -Arguments @("list", "-g", "@openai/codex", "--depth=0") -CaptureOutput
    if ($existingInstall.ExitCode -eq 0) {
      $destinationPrefix = Get-NpmGlobalPrefix -NpmCommand $npmCommand
      if (-not [string]::IsNullOrWhiteSpace($destinationPrefix)) {
        Ensure-PathStartsWith -PathEntry $destinationPrefix -PersistUserPath
      }
      Refresh-FnmEnvironment

      $reDetected = Detect-CodexInstall
      if ($reDetected.Method -eq "npm") {
        Write-Host ("OK: Codex CLI already installed ({0})" -f (Get-VersionFromCommand "codex"))
        return
      }
    }
  }

  Write-Host -NoNewline "Installing Codex CLI... "
  $result = Invoke-Tool -Command $npmCommand -Arguments @("install", "-g", "@openai/codex")
  if ($result.ExitCode -ne 0) {
    Write-Host "FAILED"
    Add-ResultError ("Codex CLI: npm install failed (exit code {0})" -f $result.ExitCode)
    return
  }

  $destinationPrefix = Get-NpmGlobalPrefix -NpmCommand $npmCommand
  if (-not [string]::IsNullOrWhiteSpace($destinationPrefix)) {
    Ensure-PathStartsWith -PathEntry $destinationPrefix -PersistUserPath
  }
  Refresh-FnmEnvironment
  if (Test-CommandAvailable "codex") {
    Write-Host "OK"
  } else {
    Write-Host "FAILED"
    Add-ResultError "Codex CLI: install completed but codex is still not on PATH."
  }
}

function Section-Setup {
  Write-Host ""
  Write-Host "=== [Setup] ==="
  Ensure-Fnm
  Ensure-NodeJs
  Ensure-Claude
  Ensure-Codex
}

function Update-Claude([string]$Method) {
  Write-Host -NoNewline ("Updating Claude Code ({0})... " -f $Method)

  switch ($Method) {
    "native" {
      $source = Get-CommandSource "claude"
      $result = Invoke-Tool -Command $source -Arguments @("update")
      if ($result.ExitCode -eq 0) {
        Write-Host "OK"
      } else {
        Write-Host "FAILED"
        Add-ResultError ("Claude Code: claude update failed (exit code {0})" -f $result.ExitCode)
      }
    }
    "npm" {
      $npmRuntime = Get-ReadyNpmRuntime -AttemptRepair -ReportError
      if (-not $npmRuntime.NpmReady) {
        Write-Host "SKIPPED"
        return
      }

      $npmCommand = $npmRuntime.NpmCommand
      $result = Invoke-Tool -Command $npmCommand -Arguments @("install", "-g", "@anthropic-ai/claude-code")
      if ($result.ExitCode -eq 0) {
        Write-Host "OK"
      } else {
        Write-Host "FAILED"
        Add-ResultError ("Claude Code: npm update failed (exit code {0})" -f $result.ExitCode)
      }
    }
  }
}

function Update-Codex([string]$Method) {
  Write-Host -NoNewline ("Updating Codex CLI ({0})... " -f $Method)

  switch ($Method) {
    "npm" {
      $npmRuntime = Get-ReadyNpmRuntime -AttemptRepair -ReportError
      if (-not $npmRuntime.NpmReady) {
        Write-Host "SKIPPED"
        return
      }

      $npmCommand = $npmRuntime.NpmCommand
      $result = Invoke-Tool -Command $npmCommand -Arguments @("install", "-g", "@openai/codex")
      if ($result.ExitCode -eq 0) {
        $destinationPrefix = Get-NpmGlobalPrefix -NpmCommand $npmCommand
        if (-not [string]::IsNullOrWhiteSpace($destinationPrefix)) {
          Ensure-PathStartsWith -PathEntry $destinationPrefix -PersistUserPath
        }
        Refresh-FnmEnvironment
        Write-Host "OK"
      } else {
        $outputText = ($result.Output -join "`n")
        if ($outputText -match "EBUSY" -or $outputText -match "resource busy or locked") {
          Write-Host "SKIPPED"
          Add-ResultWarning "Codex CLI: skipped self-update because codex.exe is locked by the current session."
        } else {
          Write-Host "FAILED"
          Add-ResultError ("Codex CLI: npm update failed (exit code {0})" -f $result.ExitCode)
        }
      }
    }
    "external" {
      Write-Host "SKIPPED"
      Add-ResultWarning "Codex CLI: resolved command is an external installation. update-ccx does not modify standalone codex.exe installs."
    }
  }
}

function Section-Update {
  Write-Host ""
  Write-Host "=== [Update] ==="

  $claudeInfo = Detect-ClaudeInstall
  $codexInfo = Detect-CodexInstall

  if ($codexInfo.Candidates.Count -gt 1) {
    $warning = Get-CodexDuplicateWarning -Candidates $codexInfo.Candidates
    if (-not [string]::IsNullOrWhiteSpace($warning)) {
      Add-ResultWarning $warning
    }
  }

  $claudeMethod = $claudeInfo.Method
  $codexMethod = $codexInfo.Method

  if ($claudeMethod -eq "not_found") {
    Write-Host "WARN: Claude Code not installed, skipping update"
    $claudeMethod = "skip"
  }
  if ($codexMethod -eq "not_found") {
    Write-Host "WARN: Codex CLI not installed, skipping update"
    $codexMethod = "skip"
  }

  Write-Host ("[Before] claude: {0} ({1}) / codex: {2} ({3})" -f `
    (Get-VersionFromCommand "claude"), $claudeMethod, `
    (Get-VersionFromCommand "codex"), $codexMethod)

  if ($claudeMethod -ne "skip") {
    Update-Claude -Method $claudeMethod
  }
  if ($codexMethod -ne "skip") {
    Update-Codex -Method $codexMethod
  }

  Write-Host ("[After]  claude: {0} / codex: {1}" -f `
    (Get-VersionFromCommand "claude"), `
    (Get-VersionFromCommand "codex"))
}

function Get-DevKitTomlValue([string]$Line, [string]$Key) {
  $pattern = '^\s*' + [regex]::Escape($Key) + '\s*=\s*(?<value>.+?)\s*(?:#.*)?$'
  if ($Line -notmatch $pattern) {
    return $null
  }

  $value = $Matches.value.Trim()
  if (
    ($value.StartsWith('"') -and $value.EndsWith('"')) -or
    ($value.StartsWith("'") -and $value.EndsWith("'"))
  ) {
    return $value.Substring(1, $value.Length - 2)
  }

  return $value
}

function Get-DevKitCodexMarketplaceState([string]$ConfigPath) {
  $exists = $false
  $sourceType = $null
  $source = $null
  $inSection = $false

  if (Test-Path -LiteralPath $ConfigPath) {
    foreach ($rawLine in (Get-Content -LiteralPath $ConfigPath -Encoding UTF8)) {
      $trimmed = $rawLine.Trim()
      if ($trimmed -match '^\[(?<section>[^\]]+)\]\s*(?:#.*)?$') {
        $section = $Matches.section
        $inSection = ($section -eq "marketplaces.murakotaro4")
        if ($inSection) {
          $exists = $true
        }
        continue
      }

      if (-not $inSection) {
        continue
      }

      $parsedSourceType = Get-DevKitTomlValue -Line $rawLine -Key "source_type"
      if ($null -ne $parsedSourceType) {
        $sourceType = $parsedSourceType
        continue
      }

      $parsedSource = Get-DevKitTomlValue -Line $rawLine -Key "source"
      if ($null -ne $parsedSource) {
        $source = $parsedSource
      }
    }
  }

  return [pscustomobject]@{
    Exists = $exists
    SourceType = $sourceType
    Source = $source
  }
}

function Test-DevKitCodexMarketplaceExpected([pscustomobject]$State) {
  if (-not $State.Exists) {
    return $false
  }

  if ($State.SourceType -and $State.SourceType.ToString().ToLowerInvariant() -eq "local") {
    return $false
  }

  if ([string]::IsNullOrWhiteSpace($State.Source)) {
    return $false
  }

  return $State.Source.ToString().ToLowerInvariant().Contains("murakotaro4/devkit")
}

function Test-DevKitCodexPluginIdentity([object]$Plugin) {
  if ($null -eq $Plugin) {
    return $false
  }

  $identityValues = New-Object System.Collections.Generic.List[string]
  foreach ($propertyName in @("id", "name", "plugin", "plugin_id", "qualified_name", "key")) {
    $property = $Plugin.PSObject.Properties[$propertyName]
    if ($null -ne $property -and -not [string]::IsNullOrWhiteSpace([string]$property.Value)) {
      $identityValues.Add(([string]$property.Value).ToLowerInvariant()) | Out-Null
    }
  }

  $marketplaceValues = New-Object System.Collections.Generic.List[string]
  foreach ($propertyName in @("marketplace", "marketplace_id", "source", "source_id", "namespace", "owner")) {
    $property = $Plugin.PSObject.Properties[$propertyName]
    if ($null -ne $property -and -not [string]::IsNullOrWhiteSpace([string]$property.Value)) {
      $marketplaceValues.Add(([string]$property.Value).ToLowerInvariant()) | Out-Null
    }
  }

  $identityText = $identityValues.ToArray() -join " "
  $marketplaceText = $marketplaceValues.ToArray() -join " "
  $hasDevKit = ($identityValues -contains "devkit") -or $identityText.Contains("devkit@murakotaro4")
  $hasMarketplace = $identityText.Contains("@murakotaro4") -or $marketplaceText.Contains("murakotaro4")
  return ($hasDevKit -and $hasMarketplace)
}

function Test-DevKitCodexPluginObjectEnabled([object]$Plugin) {
  $property = $Plugin.PSObject.Properties["enabled"]
  if ($null -eq $property) {
    return $true
  }

  if ($property.Value -is [bool]) {
    return [bool]$property.Value
  }

  return ([string]$property.Value).ToLowerInvariant() -eq "true"
}

function Get-DevKitCodexInstalledPluginCandidates([object]$Json) {
  if ($null -eq $Json) {
    return @()
  }

  if ($Json -is [array]) {
    return @($Json)
  }

  foreach ($propertyName in @("installed", "installed_plugins", "enabled", "plugins")) {
    $property = $Json.PSObject.Properties[$propertyName]
    if ($null -ne $property -and $null -ne $property.Value) {
      return @($property.Value)
    }
  }

  return @()
}

function Convert-DevKitJsonFromToolOutput([string[]]$Output) {
  $lines = @($Output)
  if ($lines.Count -eq 0) {
    return $null
  }

  for ($i = 0; $i -lt $lines.Count; $i++) {
    $candidate = ($lines[$i..($lines.Count - 1)] -join "`n").Trim()
    if ([string]::IsNullOrWhiteSpace($candidate)) {
      continue
    }

    try {
      return ($candidate | ConvertFrom-Json)
    } catch {
      continue
    }
  }

  return $null
}

function Test-DevKitCodexPluginEnabled {
  $result = Invoke-Tool -Command "codex" -Arguments @("plugin", "list", "--json") -CaptureOutput
  if ($result.ExitCode -ne 0) {
    return $false
  }

  $json = Convert-DevKitJsonFromToolOutput -Output $result.Output
  if ($null -eq $json) {
    return $false
  }

  foreach ($plugin in (Get-DevKitCodexInstalledPluginCandidates -Json $json)) {
    if ((Test-DevKitCodexPluginIdentity -Plugin $plugin) -and (Test-DevKitCodexPluginObjectEnabled -Plugin $plugin)) {
      return $true
    }
  }

  return $false
}

function Invoke-DevKitCliCommand([string]$Command, [string[]]$Arguments, [string]$FailureMessage) {
  $result = Invoke-Tool -Command $Command -Arguments $Arguments -CaptureOutput
  if ($result.ExitCode -eq 0) {
    return $true
  }

  $detail = ($result.Output -join "`n").Trim()
  if ([string]::IsNullOrWhiteSpace($detail)) {
    Add-ResultError ("{0} (exit code {1})" -f $FailureMessage, $result.ExitCode)
  } else {
    Add-ResultError ("{0} (exit code {1}): {2}" -f $FailureMessage, $result.ExitCode, $detail)
  }
  return $false
}

function Update-DevKitCodexPlugin {
  Write-Host ""
  Write-Host "=== [Codex Plugin] ==="

  if (-not (Test-CommandAvailable "codex")) {
    Write-Host "SKIPPED: Codex CLI not found"
    return
  }

  $configPath = Join-Path $env:USERPROFILE ".codex\config.toml"
  $state = Get-DevKitCodexMarketplaceState -ConfigPath $configPath
  if (-not (Test-DevKitCodexMarketplaceExpected -State $state)) {
    if ($state.Exists) {
      Write-Host "Re-registering Codex plugin marketplace murakotaro4..."
      if (-not (Invoke-DevKitCliCommand -Command "codex" -Arguments @("plugin", "marketplace", "remove", "murakotaro4") -FailureMessage "Codex plugin marketplace remove failed")) {
        return
      }
    } else {
      Write-Host "Registering Codex plugin marketplace murakotaro4..."
    }

    if (-not (Invoke-DevKitCliCommand -Command "codex" -Arguments @("plugin", "marketplace", "add", "murakotaro4/devkit") -FailureMessage "Codex plugin marketplace add failed")) {
      return
    }
  } else {
    Write-Host "OK: Codex plugin marketplace murakotaro4 already registered"
  }

  Write-Host "Upgrading Codex plugin marketplace murakotaro4..."
  if (-not (Invoke-DevKitCliCommand -Command "codex" -Arguments @("plugin", "marketplace", "upgrade", "murakotaro4") -FailureMessage "Codex plugin marketplace upgrade failed")) {
    return
  }
  Write-Host "OK: Codex plugin marketplace upgraded"

  Write-Host "Installing devkit plugin for Codex..."
  if (-not (Invoke-DevKitCliCommand -Command "codex" -Arguments @("plugin", "add", "devkit@murakotaro4") -FailureMessage "Codex plugin add failed")) {
    return
  }
}

function Remove-DevKitLegacyCursorSync([string]$RepoRoot) {
  Write-Host ""
  Write-Host "=== [Cursor Legacy Sync Migration] ==="

  $cursorRoot = Join-Path $env:USERPROFILE ".cursor"
  if (-not (Test-Path -LiteralPath $cursorRoot -PathType Container)) {
    Write-Host "SKIPPED: Cursor user directory not found"
    return
  }
  $manifestPath = Join-Path $cursorRoot ".devkit-sync-manifest.json"
  try {
    $manifestEntry = Get-ChildItem -LiteralPath $cursorRoot -Force -ErrorAction Stop |
      Where-Object { $_.Name -eq ".devkit-sync-manifest.json" } |
      Select-Object -First 1
  } catch {
    Write-Host "FAILED: Legacy Cursor sync manifest inspection"
    Add-ResultError ("Cursor legacy sync manifest inspection failed: {0}" -f $_.Exception.Message)
    return
  }
  if (-not $manifestEntry) {
    Write-Host "SKIPPED: Legacy Cursor sync manifest not found"
    return
  }

  $pythonCommand = $null
  $pythonPrefix = @()
  $candidates = @(
    [pscustomobject]@{ Command = "python3"; Prefix = @() },
    [pscustomobject]@{ Command = "python"; Prefix = @() },
    [pscustomobject]@{ Command = "py"; Prefix = @("-3") }
  )
  foreach ($candidate in $candidates) {
    $candidateCommand = [string]$candidate.Command
    $candidatePrefix = @($candidate.Prefix)
    if (-not (Get-Command $candidateCommand -ErrorAction SilentlyContinue)) {
      continue
    }
    try {
      & $candidateCommand @candidatePrefix "--version" *> $null
    } catch {
      continue
    }
    if ($LASTEXITCODE -ne 0) {
      continue
    }
    try {
      & $candidateCommand @candidatePrefix "-c" 'import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)' *> $null
    } catch {
      continue
    }
    if ($LASTEXITCODE -eq 0) {
      $pythonCommand = $candidateCommand
      $pythonPrefix = $candidatePrefix
      break
    }
  }

  if (-not $pythonCommand) {
    Add-ResultWarning "Cursor legacy sync: Python 3.10 or newer not available; prune skipped."
    Write-Host "SKIPPED: Python 3.10 or newer not found"
    return
  }

  $pruneScript = Join-Path $RepoRoot "plugins/devkit/skills/setup/scripts/prune_legacy_cursor_sync.py"
  try {
    $pruneOutput = & $pythonCommand @pythonPrefix $pruneScript --target $cursorRoot --format json 2>&1
  } catch {
    Write-Host "FAILED: Legacy Cursor sync prune"
    Add-ResultError ("Cursor legacy sync prune failed: {0}" -f $_.Exception.Message)
    return
  }
  if ($LASTEXITCODE -ne 0) {
    $detail = ($pruneOutput -join "`n").Trim()
    Write-Host "FAILED: Legacy Cursor sync prune"
    Add-ResultError ("Cursor legacy sync prune failed: {0}" -f $detail)
    return
  }
  $pruneOutput | ForEach-Object { Write-Host $_ }
}


function Update-DevKitClaudePlugin {
  Write-Host ""
  Write-Host "=== [Claude Plugin] ==="

  if (-not (Test-CommandAvailable "claude")) {
    Write-Host "SKIPPED: Claude Code not found"
    return
  }

  $marketplaceResult = Invoke-Tool -Command "claude" -Arguments @("plugin", "marketplace", "list", "--json") -CaptureOutput
  if ($marketplaceResult.ExitCode -ne 0) {
    Add-ResultError ("Claude plugin marketplace list failed (exit code {0})" -f $marketplaceResult.ExitCode)
    return
  }

  $marketplaceOutput = ($marketplaceResult.Output -join "`n").Trim()
  $marketplaces = Convert-DevKitJsonFromToolOutput -Output $marketplaceResult.Output
  if ($null -eq $marketplaces -and $marketplaceOutput -ne "[]") {
    Add-ResultError "Claude plugin marketplace list JSON parse failed"
    return
  }

  $marketplaceState = "missing"
  foreach ($marketplace in @($marketplaces)) {
    if ($null -ne $marketplace -and [string]$marketplace.name -eq "murakotaro4") {
      $marketplaceState = "replace"
      if ([string]$marketplace.source -eq "github" -and [string]$marketplace.repo -eq "murakotaro4/devkit") {
        $marketplaceState = "ok"
        break
      }
    }
  }

  if ($marketplaceState -eq "ok") {
    if (-not (Invoke-DevKitCliCommand -Command "claude" -Arguments @("plugin", "marketplace", "update", "murakotaro4") -FailureMessage "Claude plugin marketplace update failed")) {
      return
    }
  } else {
    if ($marketplaceState -eq "replace") {
      if (-not (Invoke-DevKitCliCommand -Command "claude" -Arguments @("plugin", "marketplace", "remove", "--scope", "user", "murakotaro4") -FailureMessage "Claude plugin marketplace remove failed")) {
        return
      }
    }
    if (-not (Invoke-DevKitCliCommand -Command "claude" -Arguments @("plugin", "marketplace", "add", "--scope", "user", "murakotaro4/devkit") -FailureMessage "Claude plugin marketplace add failed")) {
      return
    }
  }

  $pluginResult = Invoke-Tool -Command "claude" -Arguments @("plugin", "list", "--json") -CaptureOutput
  if ($pluginResult.ExitCode -ne 0) {
    Add-ResultError ("Claude plugin list failed (exit code {0})" -f $pluginResult.ExitCode)
    return
  }

  $pluginOutput = ($pluginResult.Output -join "`n").Trim()
  $plugins = Convert-DevKitJsonFromToolOutput -Output $pluginResult.Output
  if ($null -eq $plugins -and $pluginOutput -ne "[]") {
    Add-ResultError "Claude plugin list JSON parse failed"
    return
  }

  $pluginInstalled = $false
  foreach ($plugin in @($plugins)) {
    if ($null -ne $plugin -and [string]$plugin.id -eq "devkit@murakotaro4" -and [string]$plugin.scope -eq "user") {
      $pluginInstalled = $true
      break
    }
  }

  if ($pluginInstalled) {
    if (-not (Invoke-DevKitCliCommand -Command "claude" -Arguments @("plugin", "update", "--scope", "user", "devkit@murakotaro4") -FailureMessage "Claude DevKit plugin update failed")) {
      return
    }
  } else {
    if (-not (Invoke-DevKitCliCommand -Command "claude" -Arguments @("plugin", "install", "--scope", "user", "devkit@murakotaro4") -FailureMessage "Claude DevKit plugin install failed")) {
      return
    }
  }

  Write-Host "NOTE: Running Claude Code sessions need /reload-plugins (or restart) to apply the updated plugin."
}

function Section-DevKit {
  Write-Host ""
  Write-Host "=== [DevKit] ==="

  $logger = {
    param($Message)
    Write-Host ("INFO: {0}" -f $Message)
  }

  try {
    $repoRoot = Get-DevKitRepoRoot -UserHome $env:USERPROFILE -Logger $logger
    $managed = Install-DevKitManagedFiles -RepoRoot $repoRoot -UserHome $env:USERPROFILE
    Remove-DevKitLegacyAssets -UserHome $env:USERPROFILE -SourceRoot $repoRoot -Logger $logger
    Remove-DevKitLegacyCursorSync -RepoRoot $repoRoot

    . (Join-Path $managed.CodexBin "devkit-codex-config.ps1")
    $configResult = Install-DevKitCodexConfig -UserHome $env:USERPROFILE -OsName "windows"
    if ($configResult.BootstrappedLocalOverlay) {
      Add-ResultWarning "Codex config.local.toml was bootstrapped from the existing config."
    }
    if ($configResult.BackupPath) {
      Write-Host ("Codex config backup saved to: {0}" -f $configResult.BackupPath)
    }
    Write-Host ("OK: DevKit managed files refreshed from {0}" -f $repoRoot)
  } catch {
    Write-Host "FAILED: DevKit refresh"
    Add-ResultError ("DevKit refresh failed: {0}" -f $_.Exception.Message)
    return
  }

  Update-DevKitCodexPlugin
  Update-DevKitClaudePlugin
}

function Parse-CliArgs {
  for ($i = 0; $i -lt $CliArgs.Count; $i++) {
    $arg = $CliArgs[$i]
    switch ($arg) {
      "--version" {
        if ($CliArgs.Count -ne 1) {
          throw "INVALID_ARGS: --version cannot be combined with other arguments"
        }
        return "version"
      }
      "-v" {
        if ($CliArgs.Count -ne 1) {
          throw "INVALID_ARGS: -v cannot be combined with other arguments"
        }
        return "version"
      }
      "--cli-only" {
        $Script:CliOnly = $true
      }
      "--devkit-only" {
        $Script:DevKitOnly = $true
      }
      default {
        throw "INVALID_ARGS: unknown argument '$arg'"
      }
    }
  }

  if ($Script:CliOnly -and $Script:DevKitOnly) {
    throw "INVALID_ARGS: --cli-only and --devkit-only cannot be combined"
  }

  return "run"
}

function Show-Usage {
  Write-Host "Usage:"
  Write-Host "  update-ccx.cmd                       # update tools and DevKit"
  Write-Host "  update-ccx.cmd --version             # show current versions"
  Write-Host "  update-ccx.cmd --cli-only            # update Claude/Codex only"
  Write-Host "  update-ccx.cmd --devkit-only         # refresh DevKit managed files and Claude/Codex plugins only"
}

function Main {
  try {
    $mode = Parse-CliArgs
  } catch {
    Write-Host $_.Exception.Message
    Show-Usage
    exit 1
  }

  if ($mode -eq "version") {
    Show-Versions
    exit 0
  }

  Write-Host "=== Claude Code, Codex CLI & DevKit ==="
  Write-Host "Environment: windows"

  if (-not $Script:DevKitOnly) {
    Section-Prerequisites
    Section-Setup
    Section-Update
  }

  if (-not $Script:CliOnly) {
    Section-DevKit
  }

  if ($Script:Warnings.Count -gt 0) {
    Write-Host ""
    Write-Host "Warnings:"
    foreach ($warning in $Script:Warnings) {
      Write-Host ("  - {0}" -f $warning)
    }
  }

  if ($Script:Errors.Count -eq 0) {
    Write-Host ""
    Write-Host "OK: All done"
    exit 0
  }

  Write-Host ""
  Write-Host "Errors occurred:"
  foreach ($errorMessage in $Script:Errors) {
    Write-Host ("  - {0}" -f $errorMessage)
  }
  exit 1
}

Main
