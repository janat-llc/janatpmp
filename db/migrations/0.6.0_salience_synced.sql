-- Migration 0.6.0: Add salience_synced column to messages_metadata
-- Tracks whether Slumber Propagate has synced quality_score → Qdrant salience

ALTER TABLE messages_metadata ADD COLUMN salience_synced INTEGER DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_messages_metadata_salience_sync
    ON messages_metadata(salience_synced) WHERE salience_synced = 0;

INSERT OR IGNORE INTO schema_version (version, description) VALUES
    ('0.6.0', 'Add salience_synced column to messages_metadata for Slumber Propagate');
