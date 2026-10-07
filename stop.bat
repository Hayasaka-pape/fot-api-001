@echo off
setlocal
cd /d "%~dp0"
rem Do not add -v: stopping the app must preserve saved scenes.
docker compose down
set "studio_exit=%errorlevel%"
if not "%studio_exit%"=="0" pause
exit /b %studio_exit%
