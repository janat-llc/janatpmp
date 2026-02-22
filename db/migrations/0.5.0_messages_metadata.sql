-- ============================================================================
-- Migration 0.5.0: Messages metadata table for cognitive telemetry
-- Stores per-turn timing, RAG snapshots, keywords, labels, quality scores.
-- Also updates cdc_outbox CHECK constraint to include 'message_metadata'.
-- ============================================================================


-- ==========================================================================
-- STEP 1: Drop ALL CDC triggers that reference cdc_outbox
-- Must happen BEFORE cdc_outbox is dropped/recreated.
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
DROP TRIGGER IF EXISTS cdc_domains_insert;
DROP TRIGGER IF EXISTS cdc_domains_update;
DROP TRIGGER IF EXISTS cdc_messages_metadata_insert;


-- ==========================================================================
-- STEP 2: Recreate cdc_outbox with 'message_metadata' added to entity_type
-- ==========================================================================

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

DROP TABLE IF EXISTS cdc_outbox_new;

CREATE TABLE cdc_outbox_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    entity_type TEXT NOT NULL CHECK (entity_type IN (
        'item', 'task', 'document', 'relationship',
        'conversation', 'message', 'domain', 'message_metadata'
    )),
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
-- STEP 3: Recreate ALL existing CDC triggers
-- (Same as 0.4.2 but now includes message_metadata)
-- ==========================================================================

-- Items CDC
CREATE TRIGGER cdc_items_insert AFTER INSERT ON items
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'item', NEW.id, json_object(
        'id', NEW.id, 'entity_type', NEW.entity_type, 'domain', NEW.domain,
        'parent_id', NEW.parent_id, 'title', NEW.title,
        'description', NEW.description, 'status', NEW.status,
        'priority', NEW.priority, 'attributes', NEW.attributes, 'metadata', NEW.metadata
    ));
END;

CREATE TRIGGER cdc_items_update AFTER UPDATE ON items
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('UPDATE', 'item', NEW.id, json_object(
        'id', NEW.id, 'entity_type', NEW.entity_type, 'domain', NEW.domain,
        'parent_id', NEW.parent_id, 'title', NEW.title,
        'description', NEW.description, 'status', NEW.status,
        'priority', NEW.priority, 'attributes', NEW.attributes, 'metadata', NEW.metadata
    ));
END;

CREATE TRIGGER cdc_items_delete AFTER DELETE ON items
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('DELETE', 'item', OLD.id, json_object('id', OLD.id));
END;

-- Tasks CDC
CREATE TRIGGER cdc_tasks_insert AFTER INSERT ON tasks
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'task', NEW.id, json_object(
        'id', NEW.id, 'task_type', NEW.task_type, 'assigned_to', NEW.assigned_to,
        'target_item_id', NEW.target_item_id, 'title', NEW.title,
        'description', NEW.description, 'status', NEW.status
    ));
END;

CREATE TRIGGER cdc_tasks_update AFTER UPDATE ON tasks
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('UPDATE', 'task', NEW.id, json_object(
        'id', NEW.id, 'task_type', NEW.task_type, 'assigned_to', NEW.assigned_to,
        'target_item_id', NEW.target_item_id, 'title', NEW.title,
        'description', NEW.description, 'status', NEW.status
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
        'id', NEW.id, 'doc_type', NEW.doc_type, 'source', NEW.source,
        'title', NEW.title, 'content', NEW.content
    ));
END;

CREATE TRIGGER cdc_documents_update AFTER UPDATE ON documents
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('UPDATE', 'document', NEW.id, json_object(
        'id', NEW.id, 'doc_type', NEW.doc_type, 'source', NEW.source,
        'title', NEW.title, 'content', NEW.content
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
        'id', NEW.id, 'source_type', NEW.source_type, 'source_id', NEW.source_id,
        'target_type', NEW.target_type, 'target_id', NEW.target_id,
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

-- Domains CDC
CREATE TRIGGER cdc_domains_insert AFTER INSERT ON domains
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'domain', NEW.id, json_object(
        'id', NEW.id, 'name', NEW.name,
        'display_name', NEW.display_name, 'description', NEW.description
    ));
END;

CREATE TRIGGER cdc_domains_update AFTER UPDATE ON domains
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('UPDATE', 'domain', NEW.id, json_object(
        'id', NEW.id, 'name', NEW.name,
        'display_name', NEW.display_name, 'description', NEW.description
    ));
END;


-- ==========================================================================
-- STEP 4: Create messages_metadata table
-- ==========================================================================

CREATE TABLE messages_metadata (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    message_id TEXT NOT NULL REFERENCES messages(id) ON DELETE CASCADE,

    -- Timing (milliseconds)
    latency_total_ms    INTEGER,
    latency_rag_ms      INTEGER,
    latency_inference_ms INTEGER,

    -- RAG snapshot (frozen at turn time — survives Qdrant rebuilds)
    rag_hit_count       INTEGER DEFAULT 0,
    rag_hits_used       INTEGER DEFAULT 0,
    rag_collections     TEXT,
    rag_avg_rerank      REAL DEFAULT 0.0,
    rag_avg_salience    REAL DEFAULT 0.0,
    rag_scores          TEXT,

    -- Labels & keywords (populated by Slumber Cycle or manual tagging)
    keywords            TEXT,
    labels              TEXT,
    quality_score       REAL,

    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

CREATE UNIQUE INDEX idx_mm_message ON messages_metadata(message_id);
CREATE INDEX idx_mm_quality ON messages_metadata(quality_score) WHERE quality_score IS NOT NULL;

-- CDC trigger for messages_metadata
CREATE TRIGGER cdc_messages_metadata_insert AFTER INSERT ON messages_metadata
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'message_metadata', NEW.id, json_object(
        'id', NEW.id, 'message_id', NEW.message_id,
        'rag_hits_used', NEW.rag_hits_used, 'quality_score', NEW.quality_score
    ));
END;


-- ==========================================================================
-- STEP 5: Schema version
-- ==========================================================================

INSERT OR IGNORE INTO schema_version (version, description) VALUES
    ('0.5.0', 'Messages metadata table for cognitive telemetry — timing, RAG snapshots, quality scores');
