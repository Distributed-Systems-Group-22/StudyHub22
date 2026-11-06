#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ ! -f .env || ! -x .venv/bin/python ]]; then
    printf '%s\n' 'Run bash setup/setup-content-service.sh first.' >&2
    exit 1
fi

docker compose up -d db rabbitmq

db_ready=false
for ((attempt = 1; attempt <= 30; attempt++)); do
    if docker compose exec -T db pg_isready -q -t 1 -h 127.0.0.1; then
        db_ready=true
        break
    fi
    sleep 2
done
if [[ "$db_ready" != true ]]; then
    printf '%s\n' 'PostgreSQL did not become ready. Check docker compose logs db.' >&2
    exit 1
fi

relay_log=.venv/relay.log
relay_errors=.venv/relay-errors.log
.venv/bin/python -u relay.py > "$relay_log" 2> "$relay_errors" &
relay_pid=$!

stop_relay() {
    if kill -0 "$relay_pid" 2>/dev/null; then
        kill "$relay_pid" 2>/dev/null || true
    fi
    wait "$relay_pid" 2>/dev/null || true
}
trap stop_relay EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

relay_ready=false
for ((attempt = 1; attempt <= 60; attempt++)); do
    if ! kill -0 "$relay_pid" 2>/dev/null; then
        break
    fi
    if grep -q '^Relay ready$' "$relay_log"; then
        relay_ready=true
        break
    fi
    sleep 1
done
if [[ "$relay_ready" != true ]]; then
    printf 'Relay did not become ready. Check %s and %s.\n' "$relay_log" "$relay_errors" >&2
    exit 1
fi

printf '%s\n' 'Open http://127.0.0.1:8000/docs to test the API.'
printf '%s\n' 'Press Ctrl+C to stop the API and Relay.'
printf 'Relay output: %s\n' "$relay_log"
.venv/bin/python -m uvicorn main:app
