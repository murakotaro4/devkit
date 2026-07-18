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
  $lines.Add("## Windows font experiment")
  $lines.Add("")

  if (-not (Test-Path -LiteralPath $resultPath)) {
    $lines.Add("**RESULT MISSING (experiment script bug)**")
  } else {
    $result = Get-Content -LiteralPath $resultPath -Raw | ConvertFrom-Json
    $state = Get-ResultProperty -Result $result -Name "state" -DefaultValue "UNKNOWN"
    $namesCount = Get-ResultProperty -Result $result -Name "names_count" -DefaultValue 0
    $pwshVersion = Get-ResultProperty -Result $result -Name "pwsh_version" -DefaultValue $PSVersionTable.PSVersion.ToString()
    $udevNames = @(Get-ResultProperty -Result $result -Name "udev_names" -DefaultValue @())
    $allNames = @(Get-ResultProperty -Result $result -Name "all_names" -DefaultValue @())

    $lines.Add(('- `FONT_EXPERIMENT_RESULT={0}`' -f $state))
    $lines.Add(('- ImageOS: `{0}`' -f $env:ImageOS))
    $lines.Add(('- ImageVersion: `{0}`' -f $env:ImageVersion))
    $lines.Add(('- PowerShell: `{0}`' -f $pwshVersion))
    $lines.Add(('- Registry value count: `{0}`' -f $namesCount))
    $lines.Add("")
    $lines.Add("### UDEV registry value names")
    $lines.Add("")
    Add-CodeBlock -Lines $lines -Values $udevNames
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
      $lines.Add(('- Exit code: `{0}`' -f $installExitCode))
      $lines.Add("")
      Add-CodeBlock -Lines $lines -Values @([string]$installOutputTail)
    } elseif ($state -eq "PYTHON_UNAVAILABLE") {
      $lines.Add("")
      $lines.Add("Python was unavailable on the runner, so installation was not attempted.")
    } elseif ($state -eq "REGISTERED_MISMATCH") {
      $lines.Add("")
      $lines.Add("The installer completed, but the production registry predicate did not match all required styles.")
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
