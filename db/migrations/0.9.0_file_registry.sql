-- ============================================================
-- Migration 0.9.0: File Registry for Auto-Ingestion
-- R17: Tracks which files have been ingested so the auto-scanner
-- can skip them. Operational metadata — no CDC participation.
-- ============================================================

CREATE TABLE IF NOT EXISTS file_registry (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    file_path TEXT NOT NULL UNIQUE,
    filename TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    ingestion_type TEXT NOT NULL CHECK (
        ingestion_type IN ('claude', 'google_ai', 'markdown')
    ),
    entity_type TEXT,
    entity_count INTEGER DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'ingested' CHECK (
        status IN ('ingested', 'failed', 'skipped')
    ),
    error_message TEXT,
    ingested_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_file_registry_hash ON file_registry(content_hash);
CREATE INDEX IF NOT EXISTS idx_file_registry_type ON file_registry(ingestion_type);
CREATE INDEX IF NOT EXISTS idx_file_registry_status ON file_registry(status);

INSERT OR IGNORE INTO schema_version (version, description, applied_at) VALUES
    ('0.9.0', 'File registry for auto-ingestion tracking', datetime('now'));
