
import os
from pathlib import Path

import psycopg


DATABASE_URL = os.environ["DATABASE_URL"]


def get_connection():
    return psycopg.connect(DATABASE_URL)


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:

            # 1. Background jobs
            cur.execute("""
                CREATE TABLE IF NOT EXISTS synthesis_jobs (
                    job_id UUID PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    cache_key TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN (
                            'PENDING',
                            'RUNNING',
                            'COMPLETED',
                            'FAILED'
                        )),
                    attempts INTEGER NOT NULL DEFAULT 0,
                    error_message TEXT,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            # 2. Summary results
            cur.execute("""
                CREATE TABLE IF NOT EXISTS synthesis_results (
                    summary_id UUID PRIMARY KEY,
                    job_id UUID REFERENCES synthesis_jobs(job_id),
                    cache_key TEXT NOT NULL,
                    summary_text TEXT NOT NULL,
                    model_version TEXT NOT NULL,
                    prompt_version TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'VALID'
                        CHECK (status IN (
                            'VALID',
                            'INVALIDATED'
                        )),
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """)

            # 3. Source references
            cur.execute("""
                CREATE TABLE IF NOT EXISTS summary_sources (
                    id BIGSERIAL PRIMARY KEY,
                    summary_id UUID NOT NULL
                        REFERENCES synthesis_results(summary_id)
                        ON DELETE CASCADE,
                    document_id TEXT NOT NULL,
                    document_version INTEGER NOT NULL,
                    chunk_id TEXT,
                    page INTEGER
                )
            """)

            # Indexes
            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_jobs_user
                ON synthesis_jobs(user_id)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_results_cache
                ON synthesis_results(cache_key)
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_sources_document
                ON summary_sources(document_id)
            """)

            # Apply migrations if available
            migrations_dir = Path(__file__).resolve().parent.parent / "migrations"
            if migrations_dir.exists():
                sql_files = sorted(migrations_dir.glob("*.sql"))
                for sql_file in sql_files:
                    sql = sql_file.read_text(encoding="utf-8")
                    cur.execute(sql)
            else:
                # Direct fallback for 0001 and 0002
                cur.execute("""
                    ALTER TABLE synthesis_jobs ADD COLUMN IF NOT EXISTS document_ids JSONB;
                    ALTER TABLE synthesis_jobs ADD COLUMN IF NOT EXISTS instruction TEXT;
                    ALTER TABLE synthesis_jobs ADD COLUMN IF NOT EXISTS claim_token UUID;
                    ALTER TABLE synthesis_jobs ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ;
                    ALTER TABLE synthesis_jobs ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
                    ALTER TABLE synthesis_jobs ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

                    CREATE TABLE IF NOT EXISTS outbox_events (
                        event_id UUID PRIMARY KEY,
                        event_type TEXT NOT NULL,
                        aggregate_id UUID NOT NULL,
                        payload JSONB NOT NULL,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        published_at TIMESTAMPTZ,
                        attempts INTEGER NOT NULL DEFAULT 0,
                        available_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );

                    CREATE INDEX IF NOT EXISTS idx_outbox_unpublished ON outbox_events(created_at) WHERE published_at IS NULL;
                    CREATE INDEX IF NOT EXISTS idx_jobs_expired_lease ON synthesis_jobs(lease_until) WHERE status = 'RUNNING';
                    CREATE INDEX IF NOT EXISTS idx_outbox_ready ON outbox_events(available_at, created_at) WHERE published_at IS NULL;
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_results_unique_job ON synthesis_results(job_id) WHERE job_id IS NOT NULL;
                """)

    print("Database tables and migrations initialised.", flush=True)
