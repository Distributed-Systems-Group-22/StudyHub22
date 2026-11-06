CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY,
    original_filename TEXT NOT NULL,
    size_bytes INTEGER NOT NULL CHECK (size_bytes > 0)
);