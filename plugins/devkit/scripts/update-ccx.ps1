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
$Script:RuntimeSelection = "all"

. (Join-Path $PSScriptRoot "devkit-runtime-sync.ps1")

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

function Detect-OpencodeInstall {
  $source = Get-CommandSource "opencode"
  if ([string]::IsNullOrWhiteSpace($source)) {
    return [pscustomobject]@{ Method = "not_found"; Source = $null }
  }

  if (Test-PathContains -Path $source -Fragments @("\node_modules\", "\.npm\", "\.npm-global\", "\appdata\roaming\npm\", "\appdata\roaming\fnm\", "\appdata\local\fnm_multishells\")) {
    return [pscustomobject]@{ Method = "npm"; Source = $source }
  }

  return [pscustomobject]@{ Method = "external"; Source = $source }
}

function Show-Versions {
  Write-Host "Environment: windows"
  Write-Host ("Claude Code: {0}" -f (Get-VersionFromCommand "claude"))
  Write-Host ("Codex CLI:   {0}" -f (Get-VersionFromCommand "codex"))
  Write-Host ("opencode:    {0}" -f (Get-VersionFromCommand "opencode"))
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
    Add-ResultError "fnm: winget not available, install fnm manually and re-run update-devkit.cmd."
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

function Ensure-Opencode {
  if (Test-CommandAvailable "opencode") {
    Write-Host ("OK: opencode already installed ({0})" -f (Get-VersionFromCommand "opencode"))
    return
  }

  $npmRuntime = Get-ReadyNpmRuntime -AttemptRepair -ReportError
  $npmCommand = $npmRuntime.NpmCommand
  if (-not $npmRuntime.NpmReady) {
    return
  }

  Write-Host -NoNewline "Installing opencode... "
  $result = Invoke-Tool -Command $npmCommand -Arguments @("install", "-g", "opencode-ai")
  if ($result.ExitCode -ne 0) {
    Write-Host "FAILED"
    Add-ResultError ("opencode: npm install failed (exit code {0})" -f $result.ExitCode)
    return
  }

  Refresh-FnmEnvironment
  if (Test-CommandAvailable "opencode") {
    Write-Host "OK"
  } else {
    Write-Host "FAILED"
    Add-ResultError "opencode: install completed but opencode is still not on PATH."
  }
}

function Section-Setup {
  Write-Host ""
  Write-Host "=== [Setup] ==="
  Ensure-Fnm
  Ensure-NodeJs
  Ensure-Claude
  Ensure-Codex
  Ensure-Opencode
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
      Add-ResultWarning "Codex CLI: resolved command is an external installation. update-devkit does not modify standalone codex.exe installs."
    }
  }
}

function Update-Opencode([string]$Method) {
  Write-Host -NoNewline ("Updating opencode ({0})... " -f $Method)

  switch ($Method) {
    "npm" {
      $npmRuntime = Get-ReadyNpmRuntime -AttemptRepair -ReportError
      if (-not $npmRuntime.NpmReady) {
        Write-Host "SKIPPED"
        return
      }

      $npmCommand = $npmRuntime.NpmCommand
      $result = Invoke-Tool -Command $npmCommand -Arguments @("install", "-g", "opencode-ai") -CaptureOutput
      if ($result.ExitCode -eq 0) {
        Refresh-FnmEnvironment
        Write-Host "OK"
        return
      }

      $outputText = ($result.Output -join "`n")
      if ($outputText -match "Could not find package") {
        $reinstall = Invoke-Tool -Command $npmCommand -Arguments @("install", "-g", "opencode-ai")
        if ($reinstall.ExitCode -eq 0) {
          Refresh-FnmEnvironment
          Write-Host "OK (reinstalled)"
        } else {
          Write-Host "FAILED"
          Add-ResultError ("opencode: reinstall failed (exit code {0})" -f $reinstall.ExitCode)
        }
      } else {
        Write-Host "FAILED"
        Add-ResultError ("opencode: npm install failed (exit code {0})" -f $result.ExitCode)
      }
    }
    "external" {
      Write-Host "SKIPPED"
      Add-ResultWarning "opencode: resolved command is an external installation. update-devkit only updates npm-based installs."
    }
  }
}

function Section-Update {
  Write-Host ""
  Write-Host "=== [Update] ==="

  $claudeInfo = Detect-ClaudeInstall
  $codexInfo = Detect-CodexInstall
  $opencodeInfo = Detect-OpencodeInstall

  if ($codexInfo.Candidates.Count -gt 1) {
    $warning = Get-CodexDuplicateWarning -Candidates $codexInfo.Candidates
    if (-not [string]::IsNullOrWhiteSpace($warning)) {
      Add-ResultWarning $warning
    }
  }

  $claudeMethod = $claudeInfo.Method
  $codexMethod = $codexInfo.Method
  $opencodeMethod = $opencodeInfo.Method

  if ($claudeMethod -eq "not_found") {
    Write-Host "WARN: Claude Code not installed, skipping update"
    $claudeMethod = "skip"
  }
  if ($codexMethod -eq "not_found") {
    Write-Host "WARN: Codex CLI not installed, skipping update"
    $codexMethod = "skip"
  }
  if ($opencodeMethod -eq "not_found") {
    Write-Host "WARN: opencode not installed, skipping update"
    $opencodeMethod = "skip"
  }

  Write-Host ("[Before] claude: {0} ({1}) / codex: {2} ({3}) / opencode: {4} ({5})" -f `
    (Get-VersionFromCommand "claude"), $claudeMethod, `
    (Get-VersionFromCommand "codex"), $codexMethod, `
    (Get-VersionFromCommand "opencode"), $opencodeMethod)

  if ($claudeMethod -ne "skip") {
    Update-Claude -Method $claudeMethod
  }
  if ($codexMethod -ne "skip") {
    Update-Codex -Method $codexMethod
  }
  if ($opencodeMethod -ne "skip") {
    Update-Opencode -Method $opencodeMethod
  }

  Write-Host ("[After]  claude: {0} / codex: {1} / opencode: {2}" -f `
    (Get-VersionFromCommand "claude"), `
    (Get-VersionFromCommand "codex"), `
    (Get-VersionFromCommand "opencode"))
}

function Section-DevKitSync {
  Write-Host ""
  Write-Host "=== [DevKit Sync] ==="

  $logger = {
    param($Message)
    Write-Host ("INFO: {0}" -f $Message)
  }

  if ($Script:RuntimeSelection -in @("all", "codex")) {
    try {
      $codexResult = Sync-DevKitCodexRuntime -UserHome $env:USERPROFILE -Logger $logger -RefreshConfig
      Write-Host ("OK: Codex runtime synced from {0}" -f $codexResult.SourceRoot)
      if ($codexResult.ConfigResult.BootstrappedLocalOverlay) {
        Add-ResultWarning "Codex config.local.toml was bootstrapped from the existing config."
      }
    } catch {
      Write-Host "FAILED: Codex runtime sync"
      Add-ResultError ("Codex runtime sync failed: {0}" -f $_.Exception.Message)
    }
  }

  if ($Script:RuntimeSelection -in @("all", "opencode")) {
    try {
      $opencodeResult = Sync-DevKitOpenCodeRuntime -UserHome $env:USERPROFILE -Logger $logger
      Write-Host ("OK: OpenCode runtime synced from {0}" -f $opencodeResult.SourceRoot)
    } catch {
      Write-Host "FAILED: OpenCode runtime sync"
      Add-ResultError ("OpenCode runtime sync failed: {0}" -f $_.Exception.Message)
    }
  }
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
      "--runtime" {
        if ($i + 1 -ge $CliArgs.Count) {
          throw "INVALID_ARGS: --runtime requires codex, opencode, or all"
        }

        $i++
        $value = $CliArgs[$i].ToLowerInvariant()
        if ($value -notin @("codex", "opencode", "all")) {
          throw "INVALID_ARGS: --runtime requires codex, opencode, or all"
        }
        $Script:RuntimeSelection = $value
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
  Write-Host "  update-devkit.cmd                    # preferred name: update tools and DevKit runtimes"
  Write-Host "  update-ccx.cmd                       # compatibility alias"
  Write-Host "  update-devkit.cmd --version          # show current versions"
  Write-Host "  update-devkit.cmd --cli-only         # update Claude/Codex/OpenCode only"
  Write-Host "  update-devkit.cmd --devkit-only      # sync DevKit-managed Codex/OpenCode assets only"
  Write-Host "  update-devkit.cmd --runtime codex    # sync only Codex-managed assets"
  Write-Host "  update-devkit.cmd --runtime opencode # sync only OpenCode-managed assets"
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

  Write-Host "=== Claude Code, Codex CLI, opencode & DevKit ==="
  Write-Host "Environment: windows"

  if (-not $Script:DevKitOnly) {
    Section-Prerequisites
    Section-Setup
    Section-Update
  }

  if (-not $Script:CliOnly) {
    Section-DevKitSync
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
