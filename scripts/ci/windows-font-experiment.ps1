Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
  Write-Output ("FAIL: {0}" -f $Message)
  exit 1
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  [IO.File]::WriteAllText($Path, $Content, $utf8NoBom)
}

function Get-OutputTail([object[]]$Output, [int]$LineCount = 40) {
  return (@($Output | ForEach-Object { [string]$_ } | Select-Object -Last $LineCount) -join [Environment]::NewLine)
}

function Complete-Experiment([System.Collections.IDictionary]$Result, [string]$State) {
  $validStates = @(
    "WINGET_UNAVAILABLE",
    "INSTALL_FAILED",
    "REGISTERED_MATCH",
    "REGISTERED_MISMATCH"
  )
  if ($State -notin $validStates) {
    Fail ("unrecognized experiment state: {0}" -f $State)
  }

  $Result.state = $State
  $Result.names_count = @($Result.all_names).Count
  $json = $Result | ConvertTo-Json -Depth 6
  Write-Utf8NoBom -Path $script:ResultPath -Content ($json + [Environment]::NewLine)
  Write-Output ("OK: experiment classified as {0}" -f $State)
  Write-Output ("FONT_EXPERIMENT_RESULT={0}" -f $State)
  exit 0
}

try {
  Write-Output "=== Phase A: winget availability ==="
  $repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
  $script:ResultPath = Join-Path $env:RUNNER_TEMP "font-experiment-result.json"
  $result = [ordered]@{
    state = $null
    winget_version = $null
    install_exit_code = $null
    install_output_tail = $null
    registered = $null
    jetbrains_names = @()
    all_names = @()
    names_count = 0
    pwsh_version = $PSVersionTable.PSVersion.ToString()
  }

  $winget = Get-Command winget -ErrorAction SilentlyContinue
  if ($null -eq $winget) {
    Complete-Experiment -Result $result -State "WINGET_UNAVAILABLE"
  }

  $versionOutput = @(& $winget.Source --version 2>&1)
  $versionExitCode = $LASTEXITCODE
  $versionOutput | ForEach-Object { Write-Output ([string]$_) }
  if ($versionExitCode -ne 0) {
    Complete-Experiment -Result $result -State "WINGET_UNAVAILABLE"
  }
  $result.winget_version = (@($versionOutput | ForEach-Object { [string]$_ }) -join " ").Trim()
  Write-Output ("OK: winget is available ({0})" -f $result.winget_version)

  Write-Output "=== Phase B: font installation ==="
  $installOutput = @(& $winget.Source install --id DEVCOM.JetBrainsMonoNerdFont --exact --silent --accept-package-agreements --accept-source-agreements 2>&1)
  $installExitCode = $LASTEXITCODE
  $installOutput | ForEach-Object { Write-Output ([string]$_) }
  $result.install_exit_code = $installExitCode
  $result.install_output_tail = Get-OutputTail -Output $installOutput
  if ($installExitCode -ne 0) {
    Complete-Experiment -Result $result -State "INSTALL_FAILED"
  }
  Write-Output "OK: winget font install exited with code 0"

  Write-Output "=== Phase C: production predicate probe ==="
  $probePath = Join-Path $repoRoot "scripts\ci\font_experiment_probe.py"
  $probeOutput = @(& python $probePath 2>&1)
  $probeExitCode = $LASTEXITCODE
  if ($probeExitCode -ne 0) {
    $probeOutput | ForEach-Object { Write-Output ([string]$_) }
    Fail ("font predicate probe exited with code {0}" -f $probeExitCode)
  }

  try {
    $probe = (($probeOutput | ForEach-Object { [string]$_ }) -join [Environment]::NewLine) | ConvertFrom-Json
  } catch {
    Fail ("font predicate probe returned invalid JSON: {0}" -f $_.Exception.Message)
  }

  if ($null -eq $probe.registered -or $null -eq $probe.names -or $null -eq $probe.jetbrains_names) {
    Fail "font predicate probe JSON is missing required fields"
  }
  $result.registered = [bool]$probe.registered
  $result.jetbrains_names = @($probe.jetbrains_names)
  $result.all_names = @($probe.names)
  Write-Output ("OK: production predicate evaluated {0} registry value names" -f @($result.all_names).Count)

  if ($result.registered) {
    Complete-Experiment -Result $result -State "REGISTERED_MATCH"
  }
  Complete-Experiment -Result $result -State "REGISTERED_MISMATCH"
} catch {
  Fail ("experiment script error: {0}" -f $_.Exception.Message)
}
