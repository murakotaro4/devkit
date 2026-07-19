[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$UpdaterArgs
)

$ErrorActionPreference = "Stop"

function Find-GitBash {
  $candidates = New-Object System.Collections.Generic.List[string]
  if ($env:ProgramFiles) {
    $candidates.Add((Join-Path $env:ProgramFiles "Git\bin\bash.exe")) | Out-Null
  }
  if (${env:ProgramFiles(x86)}) {
    $candidates.Add((Join-Path ${env:ProgramFiles(x86)} "Git\bin\bash.exe")) | Out-Null
  }

  foreach ($candidate in $candidates) {
    if (-not [string]::IsNullOrWhiteSpace($candidate) -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
      return $candidate
    }
  }

  foreach ($gitPath in @(& where.exe git.exe 2>$null)) {
    if ([string]::IsNullOrWhiteSpace($gitPath)) {
      continue
    }
    $gitFile = Get-Item -LiteralPath $gitPath.Trim() -ErrorAction SilentlyContinue
    if ($null -eq $gitFile -or $gitFile.Directory.Name -ine "cmd") {
      continue
    }
    $candidate = Join-Path $gitFile.Directory.Parent.FullName "bin\bash.exe"
    if (Test-Path -LiteralPath $candidate -PathType Leaf) {
      return $candidate
    }
  }

  return $null
}

function Find-UpdateScript {
  $adjacent = Join-Path $PSScriptRoot "update-ccx.sh"
  if (Test-Path -LiteralPath $adjacent -PathType Leaf) {
    return $adjacent
  }

  $userHome = $env:HOME
  if ([string]::IsNullOrWhiteSpace($userHome)) {
    $userHome = $env:USERPROFILE
  }
  $stateFile = Join-Path $userHome ".codex\devkit\source-root.txt"
  if (Test-Path -LiteralPath $stateFile -PathType Leaf) {
    $sourceRoot = Get-Content -LiteralPath $stateFile -TotalCount 1 -ErrorAction SilentlyContinue |
      Select-Object -First 1
    if (-not [string]::IsNullOrWhiteSpace($sourceRoot)) {
      $fallback = Join-Path $sourceRoot.Trim() "plugins\devkit\scripts\update-ccx.sh"
      if (Test-Path -LiteralPath $fallback -PathType Leaf) {
        return $fallback
      }
    }
  }

  return $null
}

$bash = Find-GitBash
if ([string]::IsNullOrWhiteSpace($bash)) {
  [Console]::Error.WriteLine("ERROR: Git for Windows is required. Install Git for Windows and restart the terminal.")
  exit 1
}

$updateScript = Find-UpdateScript
if ([string]::IsNullOrWhiteSpace($updateScript)) {
  [Console]::Error.WriteLine("ERROR: update-ccx.sh was not found beside this shim or in the persisted DevKit checkout.")
  [Console]::Error.WriteLine(('Run manually: "{0}\Git\bin\bash.exe" "<DevKit checkout>\plugins\devkit\scripts\update-ccx.sh" <arguments>' -f $env:ProgramFiles))
  exit 1
}

& $bash $updateScript @UpdaterArgs
exit $LASTEXITCODE
