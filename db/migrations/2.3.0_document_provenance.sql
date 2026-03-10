-- Migration 2.3.0: Document provenance fields for rich corpus ingestion (R52)
-- Adds: author, speaker, source_type, file_created_at
-- All columns nullable, no CHECK constraints — extensible for future source types.
-- source_type free-text label: "journal", "session_minutes", "canonical", "sprint_brief", etc.

ALTER TABLE documents ADD COLUMN author TEXT;
ALTER TABLE documents ADD COLUMN speaker TEXT;
ALTER TABLE documents ADD COLUMN source_type TEXT;
ALTER TABLE documents ADD COLUMN file_created_at TEXT;

CREATE INDEX IF NOT EXISTS idx_documents_author
    ON documents(author) WHERE author IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_documents_source_type
    ON documents(source_type) WHERE source_type IS NOT NULL;

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('2.3.0', 'Add author, speaker, source_type, file_created_at to documents');
