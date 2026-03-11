-- Migration 2.3.2: Add 'dream_synthesis' to documents source CHECK constraint (R56)
-- Dream synthesis has been silently failing since R24 because 'dream_synthesis'
-- was not in the allowed source values. Every insight ever generated was discarded.
--
-- SQLite has no ALTER TABLE MODIFY CHECK — full table recreation required.

PRAGMA foreign_keys=OFF;

-- Step 1: Rename existing table
ALTER TABLE documents RENAME TO documents_old;

-- Step 2: Drop FTS table
DROP TABLE IF EXISTS documents_fts;

-- Step 3: Recreate documents with 'dream_synthesis' added to source CHECK
CREATE TABLE documents (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    doc_type TEXT NOT NULL CHECK (doc_type IN (
        'conversation',
        'file',
        'artifact',
        'research',
        'agent_output',
        'session_notes',
        'code',
        'entry'
    )),
    source TEXT NOT NULL CHECK (source IN (
        'claude_exporter',
        'upload',
        'agent',
        'generated',
        'manual',
        'dream_synthesis'
    )),
    title TEXT NOT NULL DEFAULT '',
    content TEXT,
    author TEXT,
    speaker TEXT,
    source_type TEXT,
    file_created_at TEXT,
    file_path TEXT,
    conversation_uri TEXT,
    embedding_status TEXT DEFAULT 'pending' CHECK (embedding_status IN (
        'pending',
        'processing',
        'completed',
        'failed'
    )),
    salience_score REAL DEFAULT NULL,
    salience_floor REAL DEFAULT 0.0,
    created_by TEXT DEFAULT 'mat',
    modified_by TEXT DEFAULT 'mat',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Step 4: Copy all data
INSERT INTO documents (id, doc_type, source, title, content, author, speaker,
    source_type, file_created_at, file_path, conversation_uri, embedding_status,
    salience_score, salience_floor, created_by, modified_by, created_at, updated_at)
SELECT id, doc_type, source, title, content, author, speaker,
    source_type, file_created_at, file_path, conversation_uri, embedding_status,
    salience_score, salience_floor, created_by, modified_by, created_at, updated_at
FROM documents_old;
DROP TABLE documents_old;

-- Step 5: Rebuild indexes
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_documents_author ON documents(author) WHERE author IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_documents_source_type ON documents(source_type) WHERE source_type IS NOT NULL;

-- Step 6: Recreate FTS5 virtual table
CREATE VIRTUAL TABLE documents_fts USING fts5(
    id UNINDEXED,
    doc_type UNINDEXED,
    title,
    content,
    tokenize = 'porter unicode61'
);

INSERT INTO documents_fts(id, doc_type, title, content)
SELECT id, doc_type, title, content FROM documents;

-- Step 7: Recreate all 7 triggers

-- FTS sync triggers
CREATE TRIGGER documents_fts_insert AFTER INSERT ON documents
BEGIN
    INSERT INTO documents_fts(id, doc_type, title, content)
    VALUES (NEW.id, NEW.doc_type, NEW.title, NEW.content);
END;

CREATE TRIGGER documents_fts_update AFTER UPDATE ON documents
BEGIN
    UPDATE documents_fts
    SET title = NEW.title, content = NEW.content
    WHERE id = NEW.id;
END;

CREATE TRIGGER documents_fts_delete AFTER DELETE ON documents
BEGIN
    DELETE FROM documents_fts WHERE id = OLD.id;
END;

-- Timestamp trigger
CREATE TRIGGER documents_updated_at AFTER UPDATE ON documents
BEGIN
    UPDATE documents SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- CDC triggers
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

PRAGMA foreign_keys=ON;

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('2.3.2', 'Add dream_synthesis to documents source CHECK constraint');
