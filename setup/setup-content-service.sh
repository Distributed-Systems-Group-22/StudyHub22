#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

if [[ ! -x .venv/bin/python ]]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install -r requirements.txt

.venv/bin/python - <<'PYTHON'
from pathlib import Path
import re
import secrets

env_path = Path(".env")
source = env_path if env_path.exists() else Path(".env.example")
original = source.read_text(encoding="utf-8-sig")
settings = original

for key in (
    "STUDYHUB_PROCESSING_TOKEN",
    "STUDYHUB_SEARCH_TOKEN",
    "STUDYHUB_SYNTHESIS_TOKEN",
):
    assignment = rf"^[ \t]*{key}[ \t]*="
    blank = assignment + r"[ \t]*$"
    if re.search(blank, settings, flags=re.MULTILINE):
        settings = re.sub(
            blank, f"{key}={secrets.token_hex(16)}", settings, flags=re.MULTILINE
        )
    elif not re.search(assignment, settings, flags=re.MULTILINE):
        settings = f"{settings.rstrip()}\n{key}={secrets.token_hex(16)}\n"

if not env_path.exists() or settings != original:
    env_path.write_text(settings, encoding="utf-8")
PYTHON

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

for migration in migrations/*.sql; do
    if [[ ! -f "$migration" ]]; then
        printf '%s\n' 'No SQL migrations were found.' >&2
        exit 1
    fi
    printf 'Applying %s...\n' "$migration"
    docker compose exec -T db sh -c \
        'exec psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$migration"
done

printf '%s\n' 'Setup complete. Run bash setup/start-content-service.sh to start the API and Relay.'
