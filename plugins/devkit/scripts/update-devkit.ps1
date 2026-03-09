[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$CliArgs
)

$target = Join-Path $PSScriptRoot "update-ccx.ps1"
& $target @CliArgs
exit $LASTEXITCODE
