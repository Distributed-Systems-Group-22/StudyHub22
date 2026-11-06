ALTER TABLE documents
ADD COLUMN IF NOT EXISTS processing_status TEXT NOT NULL DEFAULT 'pending'
CHECK (processing_status IN ('pending', 'succeeded', 'failed'));