#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
python3 - <<'PYTHON'
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

synthesis_defaults = [
    ("SYNTHESIS_DB", "synthesis_db"),
    ("SYNTHESIS_DB_USER", "synthesis"),
    ("SYNTHESIS_DB_PASSWORD", "synthesis_dev"),
    ("OLLAMA_BASE_URL", "http://host.docker.internal:11434"),
    ("AI_MODEL", "llama3.2:1b"),
]
for k, v in synthesis_defaults:
    assignment = rf"^[ \t]*{k}[ \t]*="
    if not re.search(assignment, settings, flags=re.MULTILINE):
        settings = f"{settings.rstrip()}\n{k}={v}\n"

if not env_path.exists() or settings != original:
    env_path.write_text(settings, encoding="utf-8")
PYTHON

printf '%s\n' 'Configuration ready. Run docker compose up --build -d.'
