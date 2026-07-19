param(
  [string]$SandboxRoot = [System.IO.Path]::GetTempPath()
)

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

# --- サンドボックス化ガード ---------------------------------------------
#
# 実 $env:USERPROFILE / $env:HOME から managed path(.codex\bin, .codex\devkit,
# .local\bin)を導出する処理は、この関数 1 つに集約する。この関数の外で
# 実環境の USERPROFILE / HOME から managed path を組み立ててはいけない
# (plugins/devkit/tests の静的検査がこれを強制する)。
function Get-RealManagedPathGuardSnapshot {
  $roots = New-Object System.Collections.Generic.List[string]
  if ($env:USERPROFILE) { $roots.Add($env:USERPROFILE) }
  if ($env:HOME -and $env:HOME -ne $env:USERPROFILE) { $roots.Add($env:HOME) }

  $managedRelativePaths = @(".codex\bin", ".codex\devkit", ".local\bin")
  $managedPaths = New-Object System.Collections.Generic.List[string]
  foreach ($root in $roots) {
    foreach ($relative in $managedRelativePaths) {
      $managedPaths.Add((Get-NormalizedPath (Join-Path $root $relative)))
    }
  }

  return [pscustomobject]@{
    OriginalUserProfile = $env:USERPROFILE
    OriginalHome        = $env:HOME
    ManagedPaths         = $managedPaths
  }
}

function Assert-SandboxCandidateSafe([string]$Candidate, [object]$Guard, [string]$CheckoutRoot) {
  $normalizedCandidate = Get-NormalizedPath $Candidate

  if ($Guard.OriginalUserProfile -and $normalizedCandidate -eq (Get-NormalizedPath $Guard.OriginalUserProfile)) {
    Fail ("sandbox candidate equals the real USERPROFILE root: {0}" -f $Candidate)
  }
  if ($Guard.OriginalHome -and $normalizedCandidate -eq (Get-NormalizedPath $Guard.OriginalHome)) {
    Fail ("sandbox candidate equals the real HOME root: {0}" -f $Candidate)
  }
  if ($normalizedCandidate -eq (Get-NormalizedPath $CheckoutRoot)) {
    Fail ("sandbox candidate equals the checkout root: {0}" -f $Candidate)
  }

  foreach ($managed in $Guard.ManagedPaths) {
    if ($normalizedCandidate -eq $managed) {
      Fail ("sandbox candidate intersects a real managed path (exact match): {0}" -f $Candidate)
    }
    if ($normalizedCandidate.StartsWith($managed + '\', [StringComparison]::Ordinal)) {
      Fail ("sandbox candidate is nested inside a real managed path: {0}" -f $Candidate)
    }
    if ($managed.StartsWith($normalizedCandidate + '\', [StringComparison]::Ordinal)) {
      Fail ("sandbox candidate would contain a real managed path: {0}" -f $Candidate)
    }
  }

  if (Test-Path -LiteralPath $Candidate) {
    Fail ("sandbox candidate already exists: {0}" -f $Candidate)
  }

  $ancestor = Split-Path -Path $Candidate -Parent
  while ($ancestor -and (Test-Path -LiteralPath $ancestor)) {
    $item = Get-Item -LiteralPath $ancestor -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
      Fail ("sandbox candidate parent hierarchy contains a reparse point: {0}" -f $ancestor)
    }
    $parent = Split-Path -Path $ancestor -Parent
    if (-not $parent -or $parent -eq $ancestor) {
      break
    }
    $ancestor = $parent
  }
}

function New-SmokeSandboxRoot([string]$Candidate) {
  New-Item -ItemType Directory -Path $Candidate -Force | Out-Null
  $item = Get-Item -LiteralPath $Candidate -Force
  if (-not $item.PSIsContainer) {
    Fail ("sandbox root was not created as a directory: {0}" -f $Candidate)
  }
  if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    Fail ("sandbox root unexpectedly has a reparse point: {0}" -f $Candidate)
  }
  return $item.FullName
}

# ガードは、候補ディレクトリを作成するより前に実行する。
$guardSnapshot = Get-RealManagedPathGuardSnapshot
$checkoutRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$sandboxCandidate = Join-Path $SandboxRoot ("devkit-updater-smoke-" + [Guid]::NewGuid().ToString())
Assert-SandboxCandidateSafe -Candidate $sandboxCandidate -Guard $guardSnapshot -CheckoutRoot $checkoutRoot
$sandboxRoot = New-SmokeSandboxRoot -Candidate $sandboxCandidate

$originalHomeEnvPresent = Test-Path Env:HOME
$originalHomeEnvValue = if ($originalHomeEnvPresent) { $env:HOME } else { $null }
$originalUserProfileEnvPresent = Test-Path Env:USERPROFILE
$originalUserProfileEnvValue = if ($originalUserProfileEnvPresent) { $env:USERPROFILE } else { $null }

$env:HOME = $sandboxRoot
$env:USERPROFILE = $sandboxRoot

try {
  $codexBin = Join-Path $sandboxRoot ".codex\bin"
  $localBin = Join-Path $sandboxRoot ".local\bin"
  $stateFile = Join-Path $sandboxRoot ".codex\devkit\source-root.txt"
  $sourceScripts = Join-Path $checkoutRoot "plugins\devkit\scripts"
  $sourceTemplates = Join-Path $checkoutRoot "plugins\devkit\templates\codex"
  $codexTemplates = Join-Path $sandboxRoot ".codex\devkit\templates\codex"
  $syncScript = Join-Path $checkoutRoot "plugins\devkit\skills\setup\scripts\sync_updater.py"
  $managedFileNames = @(
    "update-ccx.sh",
    "devkit-lib.sh",
    "update-ccx.cmd",
    "devkit-lib.ps1",
    "devkit-setup.ps1",
    "devkit-codex-config.ps1"
  )
  $managedTemplateFileNames = @("config.shared.toml", "config.windows.toml")
  $legacyCodexBinRemnantNames = @(
    "update-devkit.sh",
    "update-devkit.ps1",
    "update-devkit.cmd",
    "update-ccx.ps1"
  )
  $legacyLocalBinRemnantNames = @(
    "update-devkit",
    "update-devkit.cmd"
  )
  $managedPaths = @($managedFileNames | ForEach-Object { Join-Path $codexBin $_ })
  $managedTemplatePaths = @($managedTemplateFileNames | ForEach-Object { Join-Path $codexTemplates $_ })
  $alternateHome = Join-Path $sandboxRoot "home-mismatch-smoke"
  $userProfileCodexBin = $codexBin
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

  Write-Output ("=== Sandbox root: {0} ===" -f $sandboxRoot)

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
  # update-ccx.ps1 の委譲シムは v13 で廃止された。既存インストール済み環境に残る
  # 旧 shim を legacy remnant として seed し、sync_updater.py が prune することを検証する
  # (managed file としてはもう扱わないため copy 対象には含めない)。
  Add-Remnants
  $seededPaths = @($remnantPaths)
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
  foreach ($path in $managedPaths) {
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

  Write-Output "=== Phase boundary: reset managed HOME/USERPROFILE-mismatch state ==="
  Reset-ManagedState
  $env:HOME = $alternateHome
  $codexBin = Join-Path $alternateHome ".codex\bin"
  $localBin = Join-Path $alternateHome ".local\bin"
  $stateFile = Join-Path $alternateHome ".codex\devkit\source-root.txt"
  $codexTemplates = Join-Path $alternateHome ".codex\devkit\templates\codex"
  $managedPaths = @($managedFileNames | ForEach-Object { Join-Path $codexBin $_ })
  $managedTemplatePaths = @($managedTemplateFileNames | ForEach-Object { Join-Path $codexTemplates $_ })
  $codexRemnantPaths = @($legacyCodexBinRemnantNames | ForEach-Object { Join-Path $codexBin $_ })
  $localRemnantPaths = @($legacyLocalBinRemnantNames | ForEach-Object { Join-Path $localBin $_ })
  $remnantPaths = @($codexRemnantPaths) + @($localRemnantPaths)
  $shimPath = Join-Path $localBin "update-ccx.cmd"
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
  $shimContent = Get-Content -LiteralPath $shimPath -Raw
  $expectedShimCall = 'call "{0}" %*' -f (Join-Path $codexBin "update-ccx.cmd")
  Assert-True ($shimContent.Contains($expectedShimCall, [StringComparison]::OrdinalIgnoreCase)) "source-root updater shim targets the managed command under HOME"
  Assert-NoRemnants -Message "source-root updater"
  Assert-True (Test-Path -LiteralPath $stateFile -PathType Leaf) "source-root updater writes source-root state file"
  $persistedRoot = (Get-Content -LiteralPath $stateFile -Raw).Trim()
  Assert-True ((Get-NormalizedPath $persistedRoot) -eq (Get-NormalizedPath $checkoutRoot)) "source-root state resolves to checkout root"
  Assert-True (-not (Test-Path -LiteralPath (Join-Path $userProfileCodexBin "update-ccx.cmd"))) "Windows updater respects HOME instead of writing managed files under USERPROFILE"

  $installedPaths = @($managedPaths) + @($managedTemplatePaths) + @($shimPath)
  $run1Hashes = Get-PathHashes -Paths $installedPaths

  Write-Output "=== Phase B2: installed updater execution ==="
  $installedUpdater = $shimPath
  $run2 = Invoke-Updater -LauncherPath $installedUpdater
  Assert-True ($run2.ExitCode -eq 0) "installed updater shim exits with code 0"
  Assert-True ($run2.Output.Contains("OK All done", [StringComparison]::Ordinal)) "installed updater shim reports OK All done"
  Assert-HashesEqual -Expected $run1Hashes -Message "installed updater shim preserves managed files and shim hashes"
  Assert-NoRemnants -Message "installed updater shim"

  Write-Output "OK: Windows updater smoke completed"
} finally {
  if ($originalHomeEnvPresent) {
    $env:HOME = $originalHomeEnvValue
  } else {
    Remove-Item Env:HOME -ErrorAction SilentlyContinue
  }
  if ($originalUserProfileEnvPresent) {
    $env:USERPROFILE = $originalUserProfileEnvValue
  } else {
    Remove-Item Env:USERPROFILE -ErrorAction SilentlyContinue
  }
  if (Test-Path -LiteralPath $sandboxRoot) {
    Remove-Item -LiteralPath $sandboxRoot -Recurse -Force -ErrorAction SilentlyContinue
  }
}
