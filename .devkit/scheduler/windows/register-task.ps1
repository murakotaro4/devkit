[CmdletBinding()]
param(
  [string]$TaskName = "RepoNightlyMaintainer-devkit",
  [string]$TaskTime = "02:30"
)

$ErrorActionPreference = "Stop"
$RepoRoot = "C:\Users\murak\repos\devkit"
$CommandPath = Join-Path $RepoRoot ".devkit\bin\repo-maintainer.ps1"
$Time = [datetime]::ParseExact($TaskTime, "HH:mm", $null)
$Action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$CommandPath`""
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Description "Nightly repo maintainer for devkit" -Force | Out-Null
