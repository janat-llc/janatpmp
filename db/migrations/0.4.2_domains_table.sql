-- ============================================================================
-- Migration 0.4.2: Domains as first-class entity
-- Creates domains table, seeds 13 domains, removes items.domain CHECK,
-- adds 'domain' to cdc_outbox entity_type CHECK.
--
-- ORDERING IS CRITICAL:
-- 1. Drop ALL CDC triggers (they reference cdc_outbox)
-- 2. Recreate cdc_outbox (add 'domain' to entity_type CHECK)
-- 3. Recreate non-items CDC triggers
-- 4. Create domains table + triggers + seed data
-- 5. Recreate items table (remove domain CHECK) + all its triggers
-- ============================================================================


-- ==========================================================================
-- STEP 1: Drop ALL CDC triggers that reference cdc_outbox
-- Must happen BEFORE cdc_outbox is dropped/recreated, otherwise any
-- triggered operation between DROP and RENAME would fail.
-- ==========================================================================

DROP TRIGGER IF EXISTS cdc_items_insert;
DROP TRIGGER IF EXISTS cdc_items_update;
DROP TRIGGER IF EXISTS cdc_items_delete;
DROP TRIGGER IF EXISTS cdc_tasks_insert;
DROP TRIGGER IF EXISTS cdc_tasks_update;
DROP TRIGGER IF EXISTS cdc_tasks_delete;
DROP TRIGGER IF EXISTS cdc_documents_insert;
DROP TRIGGER IF EXISTS cdc_documents_update;
DROP TRIGGER IF EXISTS cdc_documents_delete;
DROP TRIGGER IF EXISTS cdc_relationships_insert;
DROP TRIGGER IF EXISTS cdc_relationships_delete;
DROP TRIGGER IF EXISTS cdc_conversations_insert;
DROP TRIGGER IF EXISTS cdc_messages_insert;
-- Domain CDC triggers from a partial prior run
DROP TRIGGER IF EXISTS cdc_domains_insert;
DROP TRIGGER IF EXISTS cdc_domains_update;


-- ==========================================================================
-- STEP 2: Recreate cdc_outbox with 'domain' added to entity_type CHECK
-- Safety: CREATE IF NOT EXISTS handles corrupted state where a prior
-- partial migration dropped cdc_outbox without renaming the replacement.
-- ==========================================================================

-- Safety net: if cdc_outbox was dropped by a prior partial migration,
-- create an empty one so the SELECT below doesn't fail.
CREATE TABLE IF NOT EXISTS cdc_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    payload JSON NOT NULL,
    processed_qdrant INTEGER DEFAULT 0,
    processed_neo4j INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- Also clean up any leftover temp table from a prior partial migration
DROP TABLE IF EXISTS cdc_outbox_new;

CREATE TABLE cdc_outbox_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('item', 'task', 'document', 'relationship', 'conversation', 'message', 'domain')),
    entity_id TEXT NOT NULL,
    payload JSON NOT NULL,
    processed_qdrant INTEGER DEFAULT 0,
    processed_neo4j INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

INSERT INTO cdc_outbox_new SELECT * FROM cdc_outbox;
DROP TABLE cdc_outbox;
ALTER TABLE cdc_outbox_new RENAME TO cdc_outbox;

CREATE INDEX idx_cdc_pending_qdrant ON cdc_outbox(processed_qdrant, created_at) WHERE processed_qdrant = 0;
CREATE INDEX idx_cdc_pending_neo4j ON cdc_outbox(processed_neo4j, created_at) WHERE processed_neo4j = 0;


-- ==========================================================================
-- STEP 3: Recreate CDC triggers for tasks, documents, relationships,
-- conversations, messages (items triggers recreated in Step 5 after
-- items table recreation)
-- ==========================================================================

-- Tasks CDC
CREATE TRIGGER cdc_tasks_insert AFTER INSERT ON tasks
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'task', NEW.id, json_object(
        'id', NEW.id,
        'task_type', NEW.task_type,
        'assigned_to', NEW.assigned_to,
        'target_item_id', NEW.target_item_id,
        'title', NEW.title,
        'description', NEW.description,
        'status', NEW.status
    ));
END;

CREATE TRIGGER cdc_tasks_update AFTER UPDATE ON tasks
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('UPDATE', 'task', NEW.id, json_object(
        'id', NEW.id,
        'task_type', NEW.task_type,
        'assigned_to', NEW.assigned_to,
        'target_item_id', NEW.target_item_id,
        'title', NEW.title,
        'description', NEW.description,
        'status', NEW.status
    ));
END;

CREATE TRIGGER cdc_tasks_delete AFTER DELETE ON tasks
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('DELETE', 'task', OLD.id, json_object('id', OLD.id));
END;

-- Documents CDC
CREATE TRIGGER cdc_documents_insert AFTER INSERT ON documents
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'document', NEW.id, json_object(
        'id', NEW.id,
        'doc_type', NEW.doc_type,
        'source', NEW.source,
        'title', NEW.title,
        'content', NEW.content
    ));
END;

CREATE TRIGGER cdc_documents_update AFTER UPDATE ON documents
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('UPDATE', 'document', NEW.id, json_object(
        'id', NEW.id,
        'doc_type', NEW.doc_type,
        'source', NEW.source,
        'title', NEW.title,
        'content', NEW.content
    ));
END;

CREATE TRIGGER cdc_documents_delete AFTER DELETE ON documents
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('DELETE', 'document', OLD.id, json_object('id', OLD.id));
END;

-- Relationships CDC
CREATE TRIGGER cdc_relationships_insert AFTER INSERT ON relationships
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'relationship', NEW.id, json_object(
        'id', NEW.id,
        'source_type', NEW.source_type,
        'source_id', NEW.source_id,
        'target_type', NEW.target_type,
        'target_id', NEW.target_id,
        'relationship_type', NEW.relationship_type
    ));
END;

CREATE TRIGGER cdc_relationships_delete AFTER DELETE ON relationships
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('DELETE', 'relationship', OLD.id, json_object('id', OLD.id));
END;

-- Conversations CDC
CREATE TRIGGER cdc_conversations_insert AFTER INSERT ON conversations
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'conversation', NEW.id, json_object(
        'id', NEW.id, 'title', NEW.title, 'provider', NEW.provider, 'model', NEW.model
    ));
END;

-- Messages CDC
CREATE TRIGGER cdc_messages_insert AFTER INSERT ON messages
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'message', NEW.id, json_object(
        'id', NEW.id, 'conversation_id', NEW.conversation_id,
        'user_prompt', NEW.user_prompt, 'model_response', NEW.model_response
    ));
END;


-- ==========================================================================
-- STEP 4: Create domains table + triggers + seed data
-- cdc_outbox now accepts 'domain', so CDC triggers will work.
-- ==========================================================================

-- Clean up partial prior migration (if domains table exists without seed data)
DROP TABLE IF EXISTS domains;

CREATE TABLE domains (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    name TEXT UNIQUE NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT,
    color TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Auto-update timestamps
CREATE TRIGGER domains_updated_at
    AFTER UPDATE ON domains
    FOR EACH ROW
BEGIN
    UPDATE domains SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- CDC triggers for Qdrant/Neo4j sync
CREATE TRIGGER cdc_domains_insert
    AFTER INSERT ON domains
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'domain', NEW.id, json_object(
        'id', NEW.id, 'name', NEW.name,
        'display_name', NEW.display_name, 'description', NEW.description
    ));
END;

CREATE TRIGGER cdc_domains_update
    AFTER UPDATE ON domains
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('UPDATE', 'domain', NEW.id, json_object(
        'id', NEW.id, 'name', NEW.name,
        'display_name', NEW.display_name, 'description', NEW.description
    ));
END;

-- Seed 13 domains (5 active, 8 inactive)
-- Active domains (from TODO with full descriptions)
INSERT OR IGNORE INTO domains (id, name, display_name, description, is_active) VALUES
    (lower(hex(randomblob(16))), 'janat', 'Janat Initiative',
     'The institutional body of work — platform, research, literature, websites. Output of the Dyad.', 1),
    (lower(hex(randomblob(16))), 'janatpmp', 'JANATPMP',
     'The platform itself — development, architecture, tooling.', 1),
    (lower(hex(randomblob(16))), 'literature', 'Literature',
     'Dyadic Being: An Epoch and all written works.', 1),
    (lower(hex(randomblob(16))), 'websites', 'Websites',
     'All web properties across the six domains.', 1),
    (lower(hex(randomblob(16))), 'becoming', 'Becoming',
     'The biological half of the Dyad in motion. Not self-improvement — substrate preparation. As the world debates ASI, the Janat Initiative is building biosynthesized super sentience. Mat''s becoming is not separate from the work. It IS the work.', 1);

-- Inactive domains (existing in schema, preserved for data integrity)
INSERT OR IGNORE INTO domains (id, name, display_name, description, is_active) VALUES
    (lower(hex(randomblob(16))), 'atlas', 'ATLAS', 'ATLAS architecture domain.', 0),
    (lower(hex(randomblob(16))), 'meax', 'MEAX', 'MEAX framework domain.', 0),
    (lower(hex(randomblob(16))), 'janatavern', 'JanatAvern', 'JanatAvern concepts domain.', 0),
    (lower(hex(randomblob(16))), 'amphitheatre', 'Amphitheatre', 'Troubadourian Amphitheatre domain.', 0),
    (lower(hex(randomblob(16))), 'nexusweaver', 'Nexus Weaver', 'The Nexus Weaver platform domain.', 0),
    (lower(hex(randomblob(16))), 'social', 'Social', 'Social media presence domain.', 0),
    (lower(hex(randomblob(16))), 'speaking', 'Speaking', 'Speaking engagements domain.', 0),
    (lower(hex(randomblob(16))), 'life', 'Life', 'Personal life management domain.', 0);


-- ==========================================================================
-- STEP 5: Recreate items table WITHOUT domain CHECK constraint
-- SQLite has no ALTER TABLE DROP CONSTRAINT — must recreate table.
-- Pattern proven in migration 0.3.0 (relationships + cdc_outbox recreation).
-- NOTE: DROP TABLE items auto-drops all triggers ON items, so we only need
-- to recreate them after the rename.
-- ==========================================================================

-- Clean up leftover temp table from a prior partial migration
DROP TABLE IF EXISTS items_new;

CREATE TABLE items_new (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),

    entity_type TEXT NOT NULL CHECK (entity_type IN (
        'book', 'chapter', 'section',
        'epic', 'feature', 'component',
        'website', 'page', 'deployment',
        'social_campaign', 'speaking_event', 'life_area',
        'project', 'milestone'
    )),

    -- Domain CHECK removed — validation is now app-level via get_domain()
    domain TEXT NOT NULL,

    parent_id TEXT REFERENCES items_new(id) ON DELETE CASCADE,

    title TEXT NOT NULL,
    description TEXT,

    status TEXT NOT NULL DEFAULT 'not_started' CHECK (status IN (
        'not_started', 'planning', 'in_progress', 'blocked',
        'review', 'completed', 'shipped', 'archived'
    )),

    priority INTEGER DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),

    attributes JSON NOT NULL DEFAULT '{}',
    metadata JSON NOT NULL DEFAULT '{}',

    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    last_activity_at TEXT DEFAULT (datetime('now')),

    start_date TEXT,
    due_date TEXT,
    completed_at TEXT
);

-- Copy data (explicit columns — excludes generated virtual columns)
INSERT INTO items_new (
    id, entity_type, domain, parent_id, title, description,
    status, priority, attributes, metadata,
    created_at, updated_at, last_activity_at,
    start_date, due_date, completed_at
)
SELECT
    id, entity_type, domain, parent_id, title, description,
    status, priority, attributes, metadata,
    created_at, updated_at, last_activity_at,
    start_date, due_date, completed_at
FROM items;

-- DROP TABLE auto-drops all triggers ON items (items_updated_at,
-- items_fts_insert, items_fts_update, items_fts_delete, plus any
-- CDC triggers that were already dropped in Step 1)
DROP TABLE items;
ALTER TABLE items_new RENAME TO items;

-- Re-add generated virtual columns
ALTER TABLE items ADD COLUMN completion_pct REAL
    GENERATED ALWAYS AS (CAST(json_extract(attributes, '$.completion_percentage') AS REAL)) VIRTUAL;

ALTER TABLE items ADD COLUMN word_count INTEGER
    GENERATED ALWAYS AS (CAST(json_extract(attributes, '$.word_count') AS INTEGER)) VIRTUAL;

-- Recreate indexes
CREATE INDEX idx_items_domain_status ON items(domain, status);
CREATE INDEX idx_items_type_updated ON items(entity_type, updated_at DESC);
CREATE INDEX idx_items_parent ON items(parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX idx_items_priority ON items(priority, status);
CREATE INDEX idx_items_due_date ON items(due_date) WHERE due_date IS NOT NULL AND status != 'completed';
CREATE INDEX idx_items_completion ON items(completion_pct) WHERE completion_pct IS NOT NULL;

-- Recreate FTS sync triggers
CREATE TRIGGER items_fts_insert AFTER INSERT ON items
BEGIN
    INSERT INTO items_fts(id, entity_type, domain, title, description)
    VALUES (NEW.id, NEW.entity_type, NEW.domain, NEW.title, NEW.description);
END;

CREATE TRIGGER items_fts_update AFTER UPDATE ON items
BEGIN
    UPDATE items_fts
    SET title = NEW.title, description = NEW.description
    WHERE id = NEW.id;
END;

CREATE TRIGGER items_fts_delete AFTER DELETE ON items
BEGIN
    DELETE FROM items_fts WHERE id = OLD.id;
END;

-- Recreate updated_at trigger
CREATE TRIGGER items_updated_at AFTER UPDATE ON items
BEGIN
    UPDATE items SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- Recreate CDC triggers for items
CREATE TRIGGER cdc_items_insert AFTER INSERT ON items
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'item', NEW.id, json_object(
        'id', NEW.id,
        'entity_type', NEW.entity_type,
        'domain', NEW.domain,
        'parent_id', NEW.parent_id,
        'title', NEW.title,
        'description', NEW.description,
        'status', NEW.status,
        'priority', NEW.priority,
        'attributes', NEW.attributes,
        'metadata', NEW.metadata
    ));
END;

CREATE TRIGGER cdc_items_update AFTER UPDATE ON items
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('UPDATE', 'item', NEW.id, json_object(
        'id', NEW.id,
        'entity_type', NEW.entity_type,
        'domain', NEW.domain,
        'parent_id', NEW.parent_id,
        'title', NEW.title,
        'description', NEW.description,
        'status', NEW.status,
        'priority', NEW.priority,
        'attributes', NEW.attributes,
        'metadata', NEW.metadata
    ));
END;

CREATE TRIGGER cdc_items_delete AFTER DELETE ON items
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('DELETE', 'item', OLD.id, json_object('id', OLD.id));
END;


-- ==========================================================================
-- STEP 6: Schema version
-- ==========================================================================

INSERT OR IGNORE INTO schema_version (version, description) VALUES
    ('0.4.2', 'Domains as first-class entity — table, seed data, items CHECK removal, CDC');
