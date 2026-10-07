@echo off
setlocal
cd /d "%~dp0"
docker compose down
set "studio_exit=%errorlevel%"
if not "%studio_exit%"=="0" pause
exit /b %studio_exit%
