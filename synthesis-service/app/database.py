
import os

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

    print("Database tables initialised.", flush=True)
