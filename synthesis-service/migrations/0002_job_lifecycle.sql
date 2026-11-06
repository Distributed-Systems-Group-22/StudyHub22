
BEGIN;

-- Track the current worker's ownership
ALTER TABLE synthesis_jobs
ADD COLUMN IF NOT EXISTS claim_token UUID;

-- Deadline for the running worker
ALTER TABLE synthesis_jobs
ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ;

-- Earliest time a pending job can retry
ALTER TABLE synthesis_jobs
ADD COLUMN IF NOT EXISTS next_attempt_at
TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Completion timestamp
ALTER TABLE synthesis_jobs
ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

-- Schedule outbox publication in the future
ALTER TABLE outbox_events
ADD COLUMN IF NOT EXISTS available_at
TIMESTAMPTZ NOT NULL DEFAULT NOW();

-- Find expired running jobs efficiently
CREATE INDEX IF NOT EXISTS idx_jobs_expired_lease
ON synthesis_jobs(lease_until)
WHERE status = 'RUNNING';

-- Find outbox events ready for publication
CREATE INDEX IF NOT EXISTS idx_outbox_ready
ON outbox_events(available_at, created_at)
WHERE published_at IS NULL;

-- Prevent multiple results for the same job
CREATE UNIQUE INDEX IF NOT EXISTS idx_results_unique_job
ON synthesis_results(job_id)
WHERE job_id IS NOT NULL;

COMMIT;
