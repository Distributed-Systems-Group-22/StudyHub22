BEGIN;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS owner_id TEXT;

UPDATE documents
SET owner_id = 'alice'
WHERE owner_id IS NULL;

ALTER TABLE documents ALTER COLUMN owner_id SET NOT NULL;

COMMIT;