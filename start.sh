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
studio_port=$(docker compose port studio 8000 | head -n 1 | awk -F: '{print $NF}')
studio_url="http://localhost:${studio_port}"
printf '\nStudio is ready: %s\n' "$studio_url"
if command -v open >/dev/null 2>&1; then
  open "$studio_url" || true
elif command -v xdg-open >/dev/null 2>&1; then
  xdg-open "$studio_url" >/dev/null 2>&1 || true
fi
