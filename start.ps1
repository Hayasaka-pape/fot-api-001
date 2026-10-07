$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host 'Docker Desktop is required. Install it and try again.' -ForegroundColor Red
    exit 1
}
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Start Docker Desktop, wait until it is ready, then run start.bat again.' -ForegroundColor Red
    exit 1
}
docker compose version *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Docker Compose v2 is required. Update Docker Desktop.' -ForegroundColor Red
    exit 1
}
docker compose up --build -d --wait --wait-timeout 120
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Startup failed. Run: docker compose logs studio' -ForegroundColor Red
    exit 1
}
$configuredPorts = docker compose port studio 8000
if ($LASTEXITCODE -ne 0 -or -not $configuredPorts) {
    Write-Host 'Studio started. Check its URL using: docker compose port studio 8000'
    exit 0
}
$studioPort = (($configuredPorts | Select-Object -First 1) -split ':')[-1]
$studioUrl = "http://localhost:$studioPort"
Write-Host "Studio is ready: $studioUrl" -ForegroundColor Green
Start-Process $studioUrl
