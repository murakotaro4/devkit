Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Fail([string]$Message) {
  Write-Output ("FAIL: {0}" -f $Message)
}

function Get-ResultProperty([object]$Result, [string]$Name, [object]$DefaultValue) {
  if ($null -ne $Result -and $Name -in $Result.PSObject.Properties.Name) {
    return $Result.$Name
  }
  return $DefaultValue
}

function Add-CodeBlock([System.Collections.Generic.List[string]]$Lines, [object[]]$Values) {
  $Lines.Add('```text')
  if ($Values.Count -eq 0) {
    $Lines.Add("(none)")
  } else {
    foreach ($value in $Values) {
      $Lines.Add([string]$value)
    }
  }
  $Lines.Add('```')
}

try {
  $resultPath = Join-Path $env:RUNNER_TEMP "font-experiment-result.json"
  $lines = New-Object System.Collections.Generic.List[string]
  $lines.Add("## Windows winget font experiment")
  $lines.Add("")

  if (-not (Test-Path -LiteralPath $resultPath)) {
    $lines.Add("**RESULT MISSING (experiment script bug)**")
  } else {
    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    $state = Get-ResultProperty -Result $result -Name "state" -DefaultValue "UNKNOWN"
    $wingetVersion = Get-ResultProperty -Result $result -Name "winget_version" -DefaultValue $null
    $namesCount = Get-ResultProperty -Result $result -Name "names_count" -DefaultValue 0
    $pwshVersion = Get-ResultProperty -Result $result -Name "pwsh_version" -DefaultValue $PSVersionTable.PSVersion.ToString()
    $jetbrainsNames = @(Get-ResultProperty -Result $result -Name "jetbrains_names" -DefaultValue @())
    $allNames = @(Get-ResultProperty -Result $result -Name "all_names" -DefaultValue @())

    $lines.Add(("- `FONT_EXPERIMENT_RESULT={0}`" -f $state))
    $lines.Add(("- ImageOS: `{0}`" -f $env:ImageOS))
    $lines.Add(("- ImageVersion: `{0}`" -f $env:ImageVersion))
    $lines.Add(("- PowerShell: `{0}`" -f $pwshVersion))
    $lines.Add(("- winget: `{0}`" -f $(if ($null -eq $wingetVersion) { "unavailable" } else { $wingetVersion })))
    $lines.Add(("- Registry value count: `{0}`" -f $namesCount))
    $lines.Add("")
    $lines.Add("### JetBrains registry value names")
    $lines.Add("")
    Add-CodeBlock -Lines $lines -Values $jetbrainsNames
    $lines.Add("")
    $lines.Add("<details>")
    $lines.Add("<summary>All registry value names</summary>")
    $lines.Add("")
    Add-CodeBlock -Lines $lines -Values $allNames
    $lines.Add("")
    $lines.Add("</details>")

    if ($state -eq "INSTALL_FAILED") {
      $installExitCode = Get-ResultProperty -Result $result -Name "install_exit_code" -DefaultValue "unknown"
      $installOutputTail = Get-ResultProperty -Result $result -Name "install_output_tail" -DefaultValue ""
      $lines.Add("")
      $lines.Add("### Install failure")
      $lines.Add("")
      $lines.Add(("- Exit code: `{0}`" -f $installExitCode))
      $lines.Add("")
      Add-CodeBlock -Lines $lines -Values @([string]$installOutputTail)
    }
  }

  if ([string]::IsNullOrWhiteSpace($env:GITHUB_STEP_SUMMARY)) {
    Fail "GITHUB_STEP_SUMMARY is not set"
  } else {
    Add-Content -LiteralPath $env:GITHUB_STEP_SUMMARY -Value ($lines -join [Environment]::NewLine) -Encoding utf8
    Write-Output "OK: experiment summary written"
  }
} catch {
  Fail ("could not write experiment summary: {0}" -f $_.Exception.Message)
}

exit 0
