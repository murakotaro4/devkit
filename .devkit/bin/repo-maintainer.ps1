[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$ArgsList
)

$ErrorActionPreference = "Stop"
$RepoRoot = "C:\Users\murak\repos\devkit"
$ConfigPath = Join-Path $RepoRoot ".devkit\repo-maintainer.toml"
$RunnerCandidates = @()
if (-not [string]::IsNullOrWhiteSpace($env:DEVKIT_SOURCE_ROOT)) {
  $RunnerCandidates += (Join-Path $env:DEVKIT_SOURCE_ROOT "plugins\devkit\scripts\repo_maintainer.py")
}
$RunnerCandidates += @(
  (Join-Path $HOME ".codex\devkit\source\plugins\devkit\scripts\repo_maintainer.py"),
  (Join-Path $HOME ".config\opencode\devkit\source\plugins\devkit\scripts\repo_maintainer.py"),
  (Join-Path $HOME ".claude\plugins\marketplaces\murakotaro4\plugins\devkit\scripts\repo_maintainer.py")
)

$RunnerPath = $null
foreach ($candidate in $RunnerCandidates) {
  if (Test-Path -LiteralPath $candidate) {
    $RunnerPath = $candidate
    break
  }
}
if (-not $RunnerPath) {
  throw "REPO_MAINTAINER_RUNNER_NOT_FOUND"
}

$Python = $null
foreach ($name in @("python", "py")) {
  $command = Get-Command $name -ErrorAction SilentlyContinue
  if ($command) {
    $Python = $command.Source
    break
  }
}
if (-not $Python) {
  throw "PYTHON_NOT_FOUND"
}

$InvocationArgs = @($RunnerPath, "run", "--repo", $RepoRoot, "--config", $ConfigPath)
if ($ArgsList) {
  $InvocationArgs += $ArgsList
}

& $Python @InvocationArgs
exit $LASTEXITCODE
