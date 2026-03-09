@echo off
setlocal
set "DEVKIT_SOURCE_ROOT_FILE=%USERPROFILE%\.codex\devkit\source-root.txt"
set "DEVKIT_INSTALLED_UPDATE_CCX_CMD=%USERPROFILE%\.codex\bin\update-ccx.cmd"
set "DEVKIT_UPDATE_CCX_PS1=%~dp0update-ccx.ps1"
set "DEVKIT_SOURCE_UPDATE_CCX_PS1="

if /I "%~f0"=="%DEVKIT_INSTALLED_UPDATE_CCX_CMD%" (
  for /f "usebackq delims=" %%I in (`powershell -NoProfile -ExecutionPolicy Bypass -Command ^
    "$ErrorActionPreference = 'Stop';" ^
    "$sourceRootFile = [Environment]::ExpandEnvironmentVariables($env:DEVKIT_SOURCE_ROOT_FILE);" ^
    "if (Test-Path -LiteralPath $sourceRootFile) {" ^
    "  $sourceRoot = (Get-Content -LiteralPath $sourceRootFile -Raw -Encoding UTF8).Trim();" ^
    "  if (-not [string]::IsNullOrWhiteSpace($sourceRoot) -and [IO.Directory]::Exists($sourceRoot)) {" ^
    "    $candidate = [IO.Path]::Combine($sourceRoot, 'scripts', 'update-ccx.ps1');" ^
    "    if ([IO.File]::Exists($candidate)) {" ^
    "      [Console]::Write($candidate)" ^
    "    }" ^
    "  }" ^
    "}"`) do set "DEVKIT_SOURCE_UPDATE_CCX_PS1=%%I"
)

if defined DEVKIT_SOURCE_UPDATE_CCX_PS1 (
  set "DEVKIT_UPDATE_CCX_PS1=%DEVKIT_SOURCE_UPDATE_CCX_PS1%"
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%DEVKIT_UPDATE_CCX_PS1%" %*
exit /b %ERRORLEVEL%
