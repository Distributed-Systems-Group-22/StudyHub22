"""Apply numbered SQL files once, serializing concurrent migration runners."""
import hashlib
import os
from pathlib import Path

import psycopg


def run_migrations(database_url=None, directory=None):
    directory = Path(directory or Path(__file__).with_name("migrations"))
    files = sorted(directory.glob("*.sql"))
    if not files:
        raise RuntimeError("No SQL migrations found")
    with psycopg.connect(database_url or os.environ["STUDYHUB_DATABASE_URL"], autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(220017)")
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    name TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)
            for path in files:
                sql = path.read_text(encoding="utf-8-sig")
                checksum = hashlib.sha256(sql.encode()).hexdigest()
                with conn.transaction():
                    previous = conn.execute(
                        "SELECT checksum FROM schema_migrations WHERE name = %s", (path.name,)
                    ).fetchone()
                    if previous:
                        if previous[0] != checksum:
                            raise RuntimeError(f"Applied migration changed: {path.name}")
                        continue
                    conn.execute(sql)
                    conn.execute(
                        "INSERT INTO schema_migrations (name, checksum) VALUES (%s, %s)",
                        (path.name, checksum),
                    )
                print(f"Applied {path.name}", flush=True)
        finally:
            conn.execute("SELECT pg_advisory_unlock(220017)")


if __name__ == "__main__":
    run_migrations()
