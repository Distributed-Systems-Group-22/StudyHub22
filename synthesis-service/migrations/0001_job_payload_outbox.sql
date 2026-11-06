
BEGIN;

-- 1. Store the complete summary request
ALTER TABLE synthesis_jobs
ADD COLUMN IF NOT EXISTS document_ids JSONB;

ALTER TABLE synthesis_jobs
ADD COLUMN IF NOT EXISTS instruction TEXT;

-- 2. Transactional Outbox
CREATE TABLE IF NOT EXISTS outbox_events (
    event_id UUID PRIMARY KEY,
    event_type TEXT NOT NULL,
    aggregate_id UUID NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0
);

-- 3. Index for unpublished events
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
ON outbox_events(created_at)
WHERE published_at IS NULL;

COMMIT;
