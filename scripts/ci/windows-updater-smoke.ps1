Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
  Write-Output ("FAIL: {0}" -f $Message)
  exit 1
}

function Assert-True([bool]$Condition, [string]$Message) {
  if (-not $Condition) {
    Fail $Message
  }
  Write-Output ("OK: {0}" -f $Message)
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Get-NormalizedPath([string]$Path) {
  return [IO.Path]::GetFullPath($Path).TrimEnd('\', '/').ToLowerInvariant()
}

function Get-PathHashes([string[]]$Paths) {
  $hashes = @{}
  foreach ($path in $Paths) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
      Fail ("cannot hash missing file: {0}" -f $path)
    }
    $hashes[(Get-NormalizedPath $path)] = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
  }
  return $hashes
}

function Assert-HashesEqual([hashtable]$Expected, [string]$Message) {
  foreach ($path in $Expected.Keys) {
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
      Fail ("{0}: file disappeared: {1}" -f $Message, $path)
    }
    $actual = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash
    if ($actual -ne $Expected[$path]) {
      Fail ("{0}: hash changed: {1}" -f $Message, $path)
    }
  }
  Write-Output ("OK: {0}" -f $Message)
}

function Assert-ActionPath([object[]]$Actions, [string]$Prefix, [string]$ExpectedPath) {
  $expected = Get-NormalizedPath $ExpectedPath
  $matches = @($Actions | Where-Object {
    $action = [string]$_
    if (-not $action.StartsWith($Prefix + ":", [StringComparison]::Ordinal)) {
      return $false
    }
    return (Get-NormalizedPath $action.Substring($Prefix.Length + 1)) -eq $expected
  })
  Assert-True ($matches.Count -eq 1) ("action {0} exists exactly once for {1}" -f $Prefix, $ExpectedPath)
}

function Invoke-JsonPython([string[]]$Arguments) {
  $output = @(& python @Arguments 2>&1)
  $exitCode = $LASTEXITCODE
  $output | ForEach-Object { Write-Host ([string]$_) }
  if ($exitCode -ne 0) {
    Fail ("python exited with code {0}: {1}" -f $exitCode, ($Arguments -join " "))
  }
  try {
    return (($output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine) | ConvertFrom-Json
  } catch {
    Fail ("python returned invalid JSON: {0}" -f $_.Exception.Message)
  }
}

function Invoke-Updater([string]$LauncherPath) {
  $output = @(& cmd.exe /d /c ('"{0}" --devkit-only' -f $LauncherPath) 2>&1)
  $exitCode = $LASTEXITCODE
  $output | ForEach-Object { Write-Host ([string]$_) }
  return [pscustomobject]@{
    ExitCode = $exitCode
    Output = ($output | ForEach-Object { [string]$_ }) -join [Environment]::NewLine
  }
}

$checkoutRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$codexBin = Join-Path $env:USERPROFILE ".codex\bin"
$localBin = Join-Path $env:USERPROFILE ".local\bin"
$stateFile = Join-Path $env:USERPROFILE ".codex\devkit\source-root.txt"
$sourceScripts = Join-Path $checkoutRoot "plugins\devkit\scripts"
$sourceTemplates = Join-Path $checkoutRoot "plugins\devkit\templates\codex"
$codexTemplates = Join-Path $env:USERPROFILE ".codex\devkit\templates\codex"
$syncScript = Join-Path $checkoutRoot "plugins\devkit\skills\setup\scripts\sync_updater.py"
$managedFileNames = @(
  "update-ccx.sh",
  "devkit-lib.sh",
  "update-ccx.cmd",
  "devkit-lib.ps1",
  "devkit-setup.ps1",
  "devkit-codex-config.ps1",
  "update-ccx.ps1"
)
$managedTemplateFileNames = @("config.shared.toml", "config.windows.toml")
$legacyCodexBinRemnantNames = @(
  "update-devkit.sh",
  "update-devkit.ps1",
  "update-devkit.cmd"
)
$legacyLocalBinRemnantNames = @(
  "update-devkit",
  "update-devkit.cmd"
)
$managedPaths = @($managedFileNames | ForEach-Object { Join-Path $codexBin $_ })
$managedTemplatePaths = @($managedTemplateFileNames | ForEach-Object { Join-Path $codexTemplates $_ })
$codexRemnantPaths = @($legacyCodexBinRemnantNames | ForEach-Object { Join-Path $codexBin $_ })
$localRemnantPaths = @($legacyLocalBinRemnantNames | ForEach-Object { Join-Path $localBin $_ })
$remnantPaths = @($codexRemnantPaths) + @($localRemnantPaths)
$shimPath = Join-Path $localBin "update-ccx.cmd"

function Reset-ManagedState {
  foreach ($path in @($managedPaths) + @($managedTemplatePaths) + @($remnantPaths) + @($shimPath, $stateFile)) {
    if (Test-Path -LiteralPath $path) {
      Remove-Item -LiteralPath $path -Force
    }
  }
}

function Initialize-Directories {
  New-Item -ItemType Directory -Path $codexBin -Force | Out-Null
  New-Item -ItemType Directory -Path $localBin -Force | Out-Null
}

function Add-Remnants {
  Initialize-Directories
  foreach ($path in $remnantPaths) {
    Write-Utf8NoBom -Path $path -Content ("remnant: {0}" -f [IO.Path]::GetFileName($path))
  }
}

function Assert-ManagedFilesMatchSource([string]$Message, [switch]$IncludeTemplates) {
  foreach ($name in $managedFileNames) {
    $source = Join-Path $sourceScripts $name
    $destination = Join-Path $codexBin $name
    Assert-True (Test-Path -LiteralPath $destination -PathType Leaf) ("{0}: managed file exists: {1}" -f $Message, $name)
    $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
    $destinationHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
    Assert-True ($sourceHash -eq $destinationHash) ("{0}: managed file matches source: {1}" -f $Message, $name)
  }
  if ($IncludeTemplates) {
    foreach ($name in $managedTemplateFileNames) {
      $source = Join-Path $sourceTemplates $name
      $destination = Join-Path $codexTemplates $name
      Assert-True (Test-Path -LiteralPath $destination -PathType Leaf) ("{0}: managed template exists: {1}" -f $Message, $name)
      $sourceHash = (Get-FileHash -LiteralPath $source -Algorithm SHA256).Hash
      $destinationHash = (Get-FileHash -LiteralPath $destination -Algorithm SHA256).Hash
      Assert-True ($sourceHash -eq $destinationHash) ("{0}: managed template matches source: {1}" -f $Message, $name)
    }
  }
}

function Assert-NoRemnants([string]$Message) {
  foreach ($path in $remnantPaths) {
    Assert-True (-not (Test-Path -LiteralPath $path)) ("{0}: remnant pruned: {1}" -f $Message, $path)
  }
}

Write-Output "=== Phase 0: isolated checkout preconditions ==="
if (Test-Path Env:DEVKIT_SOURCE_ROOT) {
  Remove-Item Env:DEVKIT_SOURCE_ROOT
}
& git -C $checkoutRoot symbolic-ref -q HEAD 2>$null | Out-Null
$symbolicRefExitCode = $LASTEXITCODE
Assert-True ($symbolicRefExitCode -eq 1) "checkout is detached HEAD, preventing updater git pull"

Write-Output "=== Phase A: sync_updater.py dry-run, apply, and no-op ==="
Reset-ManagedState
Initialize-Directories
$staleUpdater = Join-Path $codexBin "update-ccx.ps1"
Write-Utf8NoBom -Path $staleUpdater -Content "# stale dummy updater"
Add-Remnants
$seededPaths = @($staleUpdater) + @($remnantPaths)
$seededHashes = Get-PathHashes -Paths $seededPaths

$checkResult = Invoke-JsonPython -Arguments @($syncScript, "--check")
Assert-True ([bool]$checkResult.changed) "sync dry-run reports changed=true"
Assert-True (-not [bool]$checkResult.skipped) "sync dry-run reports skipped=false"
foreach ($path in $managedPaths) {
  Assert-ActionPath -Actions @($checkResult.actions) -Prefix "copy" -ExpectedPath $path
}
Assert-ActionPath -Actions @($checkResult.actions) -Prefix "write_shim" -ExpectedPath $shimPath
foreach ($path in $remnantPaths) {
  Assert-ActionPath -Actions @($checkResult.actions) -Prefix "prune" -ExpectedPath $path
}
Assert-HashesEqual -Expected $seededHashes -Message "sync dry-run leaves seeded file contents unchanged"
foreach ($path in $managedPaths | Where-Object { (Get-NormalizedPath $_) -ne (Get-NormalizedPath $staleUpdater) }) {
  Assert-True (-not (Test-Path -LiteralPath $path)) ("sync dry-run does not create managed file: {0}" -f $path)
}
Assert-True (-not (Test-Path -LiteralPath $shimPath)) "sync dry-run does not create shim"
foreach ($path in $remnantPaths) {
  Assert-True (Test-Path -LiteralPath $path -PathType Leaf) ("sync dry-run leaves remnant in place: {0}" -f $path)
}

$applyResult = Invoke-JsonPython -Arguments @($syncScript)
Assert-True ([bool]$applyResult.changed) "sync apply reports changed=true"
Assert-ManagedFilesMatchSource -Message "sync apply"
Assert-True (Test-Path -LiteralPath $shimPath -PathType Leaf) "sync apply creates local command shim"
Assert-NoRemnants -Message "sync apply"

$noOpResult = Invoke-JsonPython -Arguments @($syncScript)
Assert-True (-not [bool]$noOpResult.changed) "sync second apply reports changed=false"
Assert-True (@($noOpResult.actions).Count -eq 0) "sync second apply reports actions=[]"

Write-Output "=== Phase boundary: reset managed USERPROFILE state ==="
Reset-ManagedState
Add-Remnants
foreach ($path in $remnantPaths) {
  Assert-True (Test-Path -LiteralPath $path -PathType Leaf) ("phase B remnant seeded: {0}" -f $path)
}

Write-Output "=== Phase B1: source-root updater execution ==="
$sourceUpdater = Join-Path $sourceScripts "update-ccx.cmd"
$run1 = Invoke-Updater -LauncherPath $sourceUpdater
Assert-True ($run1.ExitCode -eq 0) "source-root updater exits with code 0"
Assert-True ($run1.Output.Contains("OK All done", [StringComparison]::Ordinal)) "source-root updater reports OK All done"
Assert-ManagedFilesMatchSource -Message "source-root updater" -IncludeTemplates
Assert-True (Test-Path -LiteralPath $shimPath -PathType Leaf) "source-root updater creates local command shim"
Assert-NoRemnants -Message "source-root updater"
Assert-True (Test-Path -LiteralPath $stateFile -PathType Leaf) "source-root updater writes source-root state file"
$persistedRoot = (Get-Content -LiteralPath $stateFile -Raw).Trim()
Assert-True ((Get-NormalizedPath $persistedRoot) -eq (Get-NormalizedPath $checkoutRoot)) "source-root state resolves to checkout root"

$installedPaths = @($managedPaths) + @($managedTemplatePaths) + @($shimPath)
$run1Hashes = Get-PathHashes -Paths $installedPaths

Write-Output "=== Phase B2: installed updater execution ==="
$installedUpdater = Join-Path $codexBin "update-ccx.cmd"
$run2 = Invoke-Updater -LauncherPath $installedUpdater
Assert-True ($run2.ExitCode -eq 0) "installed updater exits with code 0"
Assert-True ($run2.Output.Contains("OK All done", [StringComparison]::Ordinal)) "installed updater reports OK All done"
Assert-HashesEqual -Expected $run1Hashes -Message "installed updater preserves managed files and shim hashes"
Assert-NoRemnants -Message "installed updater"

Write-Output "OK: Windows updater smoke completed"
