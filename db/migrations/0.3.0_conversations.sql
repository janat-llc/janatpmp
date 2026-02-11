-- ============================================================================
-- Migration 0.3.0: Add conversations and messages tables (triplet schema)
-- ============================================================================

-- CONVERSATIONS: Chat sessions with context
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    title TEXT NOT NULL DEFAULT 'New Chat',

    source TEXT NOT NULL DEFAULT 'platform' CHECK (source IN (
        'platform', 'claude_export', 'imported'
    )),

    provider TEXT NOT NULL DEFAULT 'ollama',
    model TEXT NOT NULL DEFAULT 'nemotron-3-nano:latest',

    system_prompt_append TEXT DEFAULT '',

    temperature REAL DEFAULT 0.7,
    top_p REAL DEFAULT 0.9,
    max_tokens INTEGER DEFAULT 2048,

    is_active INTEGER DEFAULT 1,
    message_count INTEGER DEFAULT 0,

    conversation_uri TEXT,

    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_conversations_active ON conversations(is_active, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_source ON conversations(source, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_conversations_provider ON conversations(provider);

CREATE TRIGGER IF NOT EXISTS conversations_updated_at AFTER UPDATE ON conversations
BEGIN
    UPDATE conversations SET updated_at = datetime('now') WHERE id = NEW.id;
END;


-- MESSAGES: Triplet storage (prompt + reasoning + response)
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,

    user_prompt TEXT NOT NULL,
    model_reasoning TEXT DEFAULT '',
    model_response TEXT NOT NULL DEFAULT '',

    provider TEXT,
    model TEXT,

    tokens_prompt INTEGER DEFAULT 0,
    tokens_reasoning INTEGER DEFAULT 0,
    tokens_response INTEGER DEFAULT 0,

    tools_called JSON DEFAULT '[]',

    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, sequence);
CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at DESC);

-- FTS on messages
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    id UNINDEXED,
    conversation_id UNINDEXED,
    user_prompt,
    model_response,
    tokenize = 'porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages
BEGIN
    INSERT INTO messages_fts(id, conversation_id, user_prompt, model_response)
    VALUES (NEW.id, NEW.conversation_id, NEW.user_prompt, NEW.model_response);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages
BEGIN
    DELETE FROM messages_fts WHERE id = OLD.id;
END;

-- Update conversation message_count on insert
CREATE TRIGGER IF NOT EXISTS messages_count_insert AFTER INSERT ON messages
BEGIN
    UPDATE conversations
    SET message_count = message_count + 1, updated_at = datetime('now')
    WHERE id = NEW.conversation_id;
END;

-- CDC triggers for conversations and messages
CREATE TRIGGER IF NOT EXISTS cdc_conversations_insert AFTER INSERT ON conversations
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'conversation', NEW.id, json_object(
        'id', NEW.id, 'title', NEW.title, 'provider', NEW.provider, 'model', NEW.model
    ));
END;

CREATE TRIGGER IF NOT EXISTS cdc_messages_insert AFTER INSERT ON messages
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'message', NEW.id, json_object(
        'id', NEW.id, 'conversation_id', NEW.conversation_id,
        'user_prompt', NEW.user_prompt, 'model_response', NEW.model_response
    ));
END;


-- Recreate cdc_outbox with updated entity_type CHECK constraint
CREATE TABLE IF NOT EXISTS cdc_outbox_new (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    operation TEXT NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('item', 'task', 'document', 'relationship', 'conversation', 'message')),
    entity_id TEXT NOT NULL,
    payload JSON NOT NULL,
    processed_qdrant INTEGER DEFAULT 0,
    processed_neo4j INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

INSERT OR IGNORE INTO cdc_outbox_new SELECT * FROM cdc_outbox;
DROP TABLE IF EXISTS cdc_outbox;
ALTER TABLE cdc_outbox_new RENAME TO cdc_outbox;

CREATE INDEX idx_cdc_pending_qdrant ON cdc_outbox(processed_qdrant, created_at) WHERE processed_qdrant = 0;
CREATE INDEX idx_cdc_pending_neo4j ON cdc_outbox(processed_neo4j, created_at) WHERE processed_neo4j = 0;


-- Recreate relationships table with 'conversation' and 'message' entity types
CREATE TABLE IF NOT EXISTS relationships_new (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    source_type TEXT NOT NULL CHECK (source_type IN ('item', 'task', 'document', 'conversation', 'message')),
    source_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('item', 'task', 'document', 'conversation', 'message')),
    target_id TEXT NOT NULL,
    relationship_type TEXT NOT NULL CHECK (relationship_type IN (
        'blocks', 'enables', 'informs', 'references', 'implements',
        'documents', 'depends_on', 'parent_of', 'attached_to'
    )),
    strength TEXT DEFAULT 'hard' CHECK (strength IN ('hard', 'soft')),
    metadata JSON DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_type, source_id, target_type, target_id, relationship_type)
);

INSERT OR IGNORE INTO relationships_new SELECT * FROM relationships;

DROP TRIGGER IF EXISTS cdc_relationships_insert;
DROP TRIGGER IF EXISTS cdc_relationships_delete;
DROP TABLE IF EXISTS relationships;
ALTER TABLE relationships_new RENAME TO relationships;

CREATE INDEX idx_relationships_source ON relationships(source_type, source_id);
CREATE INDEX idx_relationships_target ON relationships(target_type, target_id);
CREATE INDEX idx_relationships_type ON relationships(relationship_type);

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


-- Schema version
INSERT OR IGNORE INTO schema_version (version, description) VALUES
    ('0.3.0', 'Add conversations and messages tables with triplet schema');
