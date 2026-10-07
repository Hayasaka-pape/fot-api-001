#!/bin/sh
set -eu
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if ! command -v docker >/dev/null 2>&1; then
  printf '%s\n' 'Docker is required. Install Docker Desktop or Docker Engine with Compose v2.' >&2
  exit 1
fi
if ! docker info >/dev/null 2>&1; then
  printf '%s\n' 'Start Docker Desktop or the Docker daemon, then try again.' >&2
  exit 1
fi
if ! docker compose version >/dev/null 2>&1; then
  printf '%s\n' 'Docker Compose v2 is required.' >&2
  exit 1
fi
docker compose up --build -d --wait --wait-timeout 120
# Query Docker instead of .env so shell overrides and dynamically assigned ports are respected.
# Avoid a pipeline here: POSIX set -e would only see awk's success and hide a Docker failure.
if ! configured_port=$(docker compose port studio 8000); then
  printf '%s\n' 'Studio is healthy and started, but its URL could not be determined. Run: docker compose port studio 8000' >&2
  exit 1
fi
studio_port=${configured_port##*:}
case "$studio_port" in
  ''|*[!0-9]*)
    printf '%s\n' 'Studio is healthy and started, but Docker returned an invalid port.' >&2
    exit 1
    ;;
esac
# Reject excessive digits before numeric comparison; some shells cannot represent a larger integer.
if [ "${#studio_port}" -gt 5 ] || [ "$studio_port" -lt 1 ] || [ "$studio_port" -gt 65535 ]; then
  printf '%s\n' 'Studio is healthy and started, but Docker returned an invalid port.' >&2
  exit 1
fi
studio_url="http://localhost:${studio_port}"
printf '\nStudio is ready: %s\n' "$studio_url"
# The printed URL remains usable when a headless environment has no browser launcher.
if command -v open >/dev/null 2>&1; then
  open "$studio_url" || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$studio_url" >/dev/null 2>&1 || true
fi
