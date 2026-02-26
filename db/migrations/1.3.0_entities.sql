-- ============================================================================
-- Migration 1.3.0: Entity extraction tables (R29: The Troubadour)
--
-- Entities are extracted concepts, decisions, milestones, people, references,
-- and emotional states discovered across conversations by the Slumber Cycle.
-- No CDC outbox changes — entities use direct Neo4j writes (same pattern as
-- dream synthesis in atlas/dream_synthesis.py).
-- ============================================================================


-- ==========================================================================
-- STEP 1: Entities table — extracted knowledge units
-- ==========================================================================

CREATE TABLE IF NOT EXISTS entities (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    entity_type     TEXT NOT NULL CHECK (entity_type IN (
        'concept', 'decision', 'milestone', 'person', 'reference', 'emotional_state'
    )),
    name            TEXT NOT NULL,
    description     TEXT DEFAULT '',
    first_seen_at   TEXT,
    last_seen_at    TEXT,
    mention_count   INTEGER DEFAULT 1,
    attributes      JSON NOT NULL DEFAULT '{}',
    metadata        JSON NOT NULL DEFAULT '{}',
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'utc')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

CREATE INDEX IF NOT EXISTS idx_entities_type ON entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_entities_type_name ON entities(entity_type, name);
CREATE INDEX IF NOT EXISTS idx_entities_updated ON entities(updated_at);

-- FTS5 for entity search
CREATE VIRTUAL TABLE IF NOT EXISTS entities_fts USING fts5(
    name, description, content=entities, content_rowid=rowid
);

-- FTS sync triggers
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

-- Auto-update updated_at on modification
CREATE TRIGGER IF NOT EXISTS entities_updated_at AFTER UPDATE ON entities
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at BEGIN
    UPDATE entities SET updated_at = datetime('now', 'utc') WHERE id = NEW.id;
END;


-- ==========================================================================
-- STEP 2: Entity mentions — links entities to source messages
-- ==========================================================================

CREATE TABLE IF NOT EXISTS entity_mentions (
    id              TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    entity_id       TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    message_id      TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL,
    relevance       REAL DEFAULT 0.5,
    context_snippet TEXT DEFAULT '',
    created_at      TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

CREATE INDEX IF NOT EXISTS idx_mentions_entity ON entity_mentions(entity_id);
CREATE INDEX IF NOT EXISTS idx_mentions_message ON entity_mentions(message_id);
CREATE INDEX IF NOT EXISTS idx_mentions_conversation ON entity_mentions(conversation_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_mentions_unique ON entity_mentions(entity_id, message_id);


-- ==========================================================================
-- STEP 3: Extraction tracking on messages_metadata
-- ==========================================================================

ALTER TABLE messages_metadata ADD COLUMN extracted_at TEXT;


-- ==========================================================================
-- STEP 4: Schema version
-- ==========================================================================

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('1.3.0', 'R29: Entity extraction tables + tracking');
