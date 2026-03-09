-- ============================================================================
-- Migration 2.1.0: Expand entity_type CHECK constraint (R50: Foundation Lock)
--
-- Adds 6 new entity types: experiment, bug, spike, research, debt, initiative
-- SQLite does not support ALTER TABLE ... ADD CONSTRAINT, so full table
-- recreation is required. No CDC triggers on entities (direct Neo4j writes).
-- ============================================================================

PRAGMA foreign_keys = OFF;

BEGIN;

-- STEP 1: Drop FTS triggers and FTS virtual table
DROP TRIGGER IF EXISTS entities_fts_insert;
DROP TRIGGER IF EXISTS entities_fts_update;
DROP TRIGGER IF EXISTS entities_fts_delete;
DROP TRIGGER IF EXISTS entities_updated_at;
DROP TABLE IF EXISTS entities_fts;

-- STEP 2: Rename original to backup
ALTER TABLE entities RENAME TO entities_backup;

-- STEP 3: Create with expanded CHECK constraint
CREATE TABLE entities (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    entity_type     TEXT NOT NULL CHECK (entity_type IN (
        'concept', 'decision', 'milestone', 'person', 'reference', 'emotional_state',
        'experiment', 'bug', 'spike', 'research', 'debt', 'initiative'
    )),
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    first_seen_at   TEXT,
    last_seen_at    TEXT,
    mention_count   INTEGER DEFAULT 1,
    salience        REAL DEFAULT 0.5,
    attributes      JSON NOT NULL DEFAULT '{}',
    metadata        JSON NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- STEP 4: Copy all data
INSERT INTO entities SELECT * FROM entities_backup;

-- STEP 5: Drop backup
DROP TABLE entities_backup;

-- STEP 6: Recreate indexes
CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_type_name ON entities(entity_type, name);
CREATE INDEX IF NOT EXISTS idx_entities_updated ON entities(updated_at);

-- STEP 7: Recreate FTS virtual table and populate
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    name, description, content=entities, content_rowid=rowid
);
INSERT INTO entities_fts(rowid, name, description)
    SELECT rowid, name, description FROM entities;

-- STEP 8: Recreate triggers
CREATE TRIGGER IF NOT EXISTS entities_fts_insert AFTER INSERT ON entities BEGIN
    INSERT INTO entities_fts(rowid, name, description)
    VALUES (NEW.rowid, NEW.name, NEW.description);
END;

CREATE TRIGGER IF NOT EXISTS entities_fts_update AFTER UPDATE ON entities BEGIN
    UPDATE entities_fts SET name = NEW.name, description = NEW.description
    WHERE rowid = NEW.rowid;
END;

CREATE TRIGGER IF NOT EXISTS entities_fts_delete AFTER DELETE ON entities BEGIN
    DELETE FROM entities_fts WHERE rowid = OLD.rowid;
END;

CREATE TRIGGER IF NOT EXISTS entities_updated_at AFTER UPDATE ON entities
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at BEGIN
    UPDATE entities SET updated_at = datetime('now', 'utc') WHERE id = NEW.id;
END;

-- STEP 9: Schema version
INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('2.1.0', 'R50: Expand entity_type CHECK — add experiment, bug, spike, research, debt, initiative');

COMMIT;

PRAGMA foreign_keys = ON;
