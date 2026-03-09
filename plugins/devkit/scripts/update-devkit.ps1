[CmdletBinding()]
param(
  [Parameter(ValueFromRemainingArguments = $true)]
  [string[]]$CliArgs
)

$target = Join-Path $PSScriptRoot "update-ccx.ps1"
if ($null -ne $CliArgs -and $CliArgs.Count -gt 0) {
  & $target @CliArgs
} else {
  & $target
}
exit $LASTEXITCODE
