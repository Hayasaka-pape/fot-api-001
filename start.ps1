$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Write-Host 'Docker Desktop is required. Install it and try again.' -ForegroundColor Red
    exit 1
}
# PowerShell 5.1 treats redirected native stderr as an error, even for successful Docker warnings.
# Keep that preference local and use the CLI exit code, instead of treating every stderr line as failure.
function Invoke-DockerProbe {
    param([string[]]$DockerArguments)
    $ErrorActionPreference = 'Continue'
    try {
        $output = & docker @DockerArguments 2>$null
        return @{ ExitCode = $LASTEXITCODE; Output = $output }
    } catch {
        return @{ ExitCode = 1; Output = $null }
    }
}
$dockerInfo = Invoke-DockerProbe -DockerArguments @('info')
if ($dockerInfo.ExitCode -ne 0) {
    Write-Host 'Start Docker Desktop, wait until it is ready, then run start.bat again.' -ForegroundColor Red
    exit 1
}
$composeVersion = Invoke-DockerProbe -DockerArguments @('compose', 'version')
if ($composeVersion.ExitCode -ne 0) {
    Write-Host 'Docker Compose v2 is required. Update Docker Desktop.' -ForegroundColor Red
    exit 1
}
# A running container can still be initializing, so wait for its local healthcheck before opening UI.
docker compose up --build -d --wait --wait-timeout 120
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Startup failed. Run: docker compose logs studio' -ForegroundColor Red
    exit 1
}
$portLookup = Invoke-DockerProbe -DockerArguments @('compose', 'port', 'studio', '8000')
$configuredPorts = $portLookup.Output
if ($portLookup.ExitCode -ne 0 -or -not $configuredPorts) {
    Write-Host 'Studio is healthy and started, but its URL could not be determined. Run: docker compose port studio 8000' -ForegroundColor Red
    exit 1
}
# Read the actual binding; parsing .env would miss shell overrides and Docker-assigned ports.
$studioPort = (($configuredPorts | Select-Object -First 1) -split ':')[-1]
if ($studioPort -notmatch '^\d{1,5}$' -or [int]$studioPort -lt 1 -or [int]$studioPort -gt 65535) {
    Write-Host 'Studio is healthy and started, but Docker returned an invalid port. Run: docker compose port studio 8000' -ForegroundColor Red
    exit 1
}
$studioUrl = "http://localhost:$studioPort"
Write-Host "Studio is ready: $studioUrl" -ForegroundColor Green
# Browser associations can be absent on a headless PC; that does not invalidate a healthy service.
try {
    Start-Process $studioUrl
} catch {
    Write-Host "Open $studioUrl in your browser. Automatic browser launch was unavailable."
}
