#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
if [[ ! -f .env ]]; then
    printf '%s\n' 'Run bash setup/setup-content-service.sh first.' >&2
    exit 1
fi
docker compose up --build -d
printf '%s\n' 'API: http://127.0.0.1:8000/docs' 'Logs: docker compose logs -f content-api content-relay' 'Stop: docker compose down'
