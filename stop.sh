#!/bin/sh
set -eu
cd -- "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
# Do not add -v: stopping the app must preserve the user's saved scenes.
docker compose down
