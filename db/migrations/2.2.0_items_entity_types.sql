-- ============================================================================
-- Migration 2.2.0: Expand items entity_type CHECK constraint (R50: Foundation Lock)
--
-- Adds 6 new entity types: experiment, bug, spike, research, debt, initiative
-- SQLite does not support ALTER TABLE ... ADD CONSTRAINT, so full table
-- recreation is required. Generated columns and all constraints must be
-- preserved exactly.
-- ============================================================================

PRAGMA foreign_keys = OFF;

BEGIN;

-- STEP 1: Drop triggers that reference items
DROP TRIGGER IF EXISTS items_updated_at;

-- STEP 2: Rename original to backup
ALTER TABLE items RENAME TO items_backup;

-- STEP 3: Create with expanded CHECK constraint
CREATE TABLE items (
    -- Core identification
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),

    -- Type and domain classification
    entity_type TEXT NOT NULL CHECK (entity_type IN (
        -- Literature domain
        'book', 'chapter', 'section',
        -- Code domains (JANAT, ATLAS, MEAX, etc.)
        'epic', 'feature', 'component',
        -- Website domain
        'website', 'page', 'deployment',
        -- Other domains
        'social_campaign', 'speaking_event', 'life_area',
        -- Generic
        'project', 'milestone',
        -- R50: new types
        'experiment', 'bug', 'spike', 'research', 'debt', 'initiative'
    )),

    -- Domain validation is app-level via get_domain() against the domains table
    domain TEXT NOT NULL,

    -- Hierarchy support
    parent_id TEXT REFERENCES items(id) ON DELETE CASCADE,

    -- Core attributes
    title TEXT NOT NULL,
    description TEXT,

    -- Status tracking
    status TEXT NOT NULL DEFAULT 'not_started' CHECK (status IN (
        'not_started',
        'planning',
        'in_progress',
        'blocked',
        'review',
        'completed',
        'shipped',
        'archived'
    )),

    priority INTEGER DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),

    -- Domain-specific attributes stored as JSON
    attributes JSON NOT NULL DEFAULT '{}',

    -- Additional metadata
    metadata JSON NOT NULL DEFAULT '{}',

    -- Temporal tracking
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_activity_at TEXT DEFAULT (datetime('now')),

    -- Target dates
    start_date TEXT,
    due_date TEXT,
    completed_at TEXT,

    -- Generated columns (must match original exactly)
    completion_pct REAL
        GENERATED ALWAYS AS (CAST(json_extract(attributes, '$.completion_percentage') AS REAL)) VIRTUAL,
    word_count INTEGER
        GENERATED ALWAYS AS (CAST(json_extract(attributes, '$.word_count') AS INTEGER)) VIRTUAL,

    created_by TEXT NOT NULL DEFAULT 'unknown',
    modified_by TEXT NOT NULL DEFAULT 'unknown'
);

-- STEP 4: Copy all data (exclude generated columns)
INSERT INTO items (
    id, entity_type, domain, parent_id, title, description,
    status, priority, attributes, metadata,
    created_at, updated_at, last_activity_at,
    start_date, due_date, completed_at,
    created_by, modified_by
)
SELECT
    id, entity_type, domain, parent_id, title, description,
    status, priority, attributes, metadata,
    created_at, updated_at, last_activity_at,
    start_date, due_date, completed_at,
    created_by, modified_by
FROM items_backup;

-- STEP 5: Drop backup
DROP TABLE items_backup;

-- STEP 6: Recreate indexes
CREATE INDEX IF NOT EXISTS idx_items_domain ON items(domain);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_entity_type ON items(entity_type);
CREATE INDEX IF NOT EXISTS idx_items_parent ON items(parent_id);
CREATE INDEX IF NOT EXISTS idx_items_updated ON items(updated_at);

-- STEP 7: Recreate trigger
CREATE TRIGGER IF NOT EXISTS items_updated_at
AFTER UPDATE ON items
FOR EACH ROW WHEN NEW.updated_at = OLD.updated_at
BEGIN
    UPDATE items SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- STEP 8: Schema version
INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('2.2.0', 'R50: Expand items entity_type CHECK — add experiment, bug, spike, research, debt, initiative');

COMMIT;

PRAGMA foreign_keys = ON;
