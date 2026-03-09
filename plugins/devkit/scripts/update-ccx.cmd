@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update-ccx.ps1" %*
exit /b %ERRORLEVEL%
