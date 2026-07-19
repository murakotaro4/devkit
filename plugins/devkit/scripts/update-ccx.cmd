@echo off
setlocal

set "DEVKIT_BASH="
if exist "%ProgramFiles%\Git\bin\bash.exe" set "DEVKIT_BASH=%ProgramFiles%\Git\bin\bash.exe"
if not defined DEVKIT_BASH if defined ProgramFiles(x86) if exist "%ProgramFiles(x86)%\Git\bin\bash.exe" set "DEVKIT_BASH=%ProgramFiles(x86)%\Git\bin\bash.exe"

if not defined DEVKIT_BASH (
  for /f "usebackq delims=" %%G in (`where git.exe 2^>nul`) do if not defined DEVKIT_BASH call :resolve_bash_from_git "%%~fG"
)

if not defined DEVKIT_BASH (
  echo ERROR: Git for Windows is required. Install Git for Windows and restart the terminal. 1>&2
  exit /b 1
)

set "DEVKIT_UPDATE_SH=%~dp0update-ccx.sh"
if not exist "%DEVKIT_UPDATE_SH%" call :resolve_update_script

if not exist "%DEVKIT_UPDATE_SH%" (
  echo ERROR: update-ccx.sh was not found beside this launcher or in the persisted DevKit checkout. 1>&2
  echo Run manually: "%%ProgramFiles%%\Git\bin\bash.exe" "^<DevKit checkout^>\plugins\devkit\scripts\update-ccx.sh" %%* 1>&2
  exit /b 1
)

"%DEVKIT_BASH%" "%DEVKIT_UPDATE_SH%" %*
exit /b %ERRORLEVEL%

:resolve_bash_from_git
for %%D in ("%~dp1.") do if /I "%%~nxD"=="cmd" for %%B in ("%~dp1..\bin\bash.exe") do if exist "%%~fB" set "DEVKIT_BASH=%%~fB"
exit /b 0

:resolve_update_script
set "DEVKIT_SOURCE_ROOT="
if exist "%USERPROFILE%\.codex\devkit\source-root.txt" set /p "DEVKIT_SOURCE_ROOT="<"%USERPROFILE%\.codex\devkit\source-root.txt"
if defined DEVKIT_SOURCE_ROOT set "DEVKIT_UPDATE_SH=%DEVKIT_SOURCE_ROOT%\plugins\devkit\scripts\update-ccx.sh"
exit /b 0
