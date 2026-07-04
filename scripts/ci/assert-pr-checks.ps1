param(
  [Parameter(Mandatory = $true)]
  [int]$PrNumber,

  [string]$Repo = "",
  [string]$WorkflowName = "DevKit Checks",
  [int]$TimeoutSeconds = 300,
  [int]$PollIntervalSeconds = 10
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
  Write-Error $Message
  exit 2
}

function Get-AllWorkflows([string]$RepoName) {
  $page = 1
  $all = @()
  while ($true) {
    $resp = gh api "repos/$RepoName/actions/workflows?per_page=100&page=$page" | ConvertFrom-Json
    $chunk = @($resp.workflows)
    if ($chunk.Count -eq 0) {
      break
    }
    $all += $chunk
    if ($chunk.Count -lt 100) {
      break
    }
    $page += 1
  }
  return $all
}

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
  Fail "gh CLI is required. Install from https://cli.github.com/"
}

if ([string]::IsNullOrWhiteSpace($Repo)) {
  $repoOut = gh repo view --json nameWithOwner --jq ".nameWithOwner" 2>$null
  if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($repoOut)) {
    Fail "Could not resolve repository from current directory. Pass -Repo <owner/name>."
  }
  $Repo = $repoOut.Trim()
}

if ([string]::IsNullOrWhiteSpace($Repo)) {
  Fail "Could not resolve repository. Pass -Repo <owner/name>."
}

$pr = gh api "repos/$Repo/pulls/$PrNumber" | ConvertFrom-Json
$headSha = $pr.head.sha

if ([string]::IsNullOrWhiteSpace($headSha)) {
  Fail "Could not resolve PR head SHA for PR #$PrNumber."
}

$deadline = (Get-Date).AddSeconds($TimeoutSeconds)
$workflowId = $null
$lastWorkflowState = ""
while ((Get-Date) -lt $deadline) {
  $workflow = Get-AllWorkflows -RepoName $Repo |
    Where-Object { $_.name -eq $WorkflowName } |
    Select-Object -First 1

  if ($null -ne $workflow) {
    $lastWorkflowState = [string]$workflow.state
    if ($workflow.state -eq "active") {
      $workflowId = [int64]$workflow.id
    }
  }

  if ($null -eq $workflowId) {
    Start-Sleep -Seconds $PollIntervalSeconds
    continue
  }

  $runs = gh api "repos/$Repo/actions/runs?event=pull_request&head_sha=$headSha&per_page=50" | ConvertFrom-Json
  $match = $runs.workflow_runs |
    Where-Object {
      if ($_.workflow_id -ne $workflowId) { return $false }
      $prs = @($_.pull_requests)
      return (@($prs | Where-Object { $_.number -eq $PrNumber }).Count -gt 0)
    } |
    Sort-Object -Property created_at -Descending |
    Select-Object -First 1

  if ($null -ne $match) {
    Write-Output ("OK: workflow run detected for PR #{0}" -f $PrNumber)
    Write-Output ("workflow={0} run_id={1} status={2} conclusion={3}" -f $WorkflowName, $match.id, $match.status, $match.conclusion)
    Write-Output ("url={0}" -f $match.html_url)
    exit 0
  }

  Start-Sleep -Seconds $PollIntervalSeconds
}

if ($null -eq $workflowId) {
  Fail ("Workflow '{0}' was not active in {1} within {2}s (last_state={3})." -f $WorkflowName, $Repo, $TimeoutSeconds, $lastWorkflowState)
}

Fail ("No '$WorkflowName' run found for PR #{0} (head_sha={1}) within {2}s. Try: gh pr checks {0} --watch" -f $PrNumber, $headSha, $TimeoutSeconds)
