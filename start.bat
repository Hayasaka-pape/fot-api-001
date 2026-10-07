@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
rem Preserve the launch result before pause can replace errorlevel.
set "studio_exit=%errorlevel%"
if not "%studio_exit%"=="0" pause
exit /b %studio_exit%
