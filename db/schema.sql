-- ============================================================================
-- JANATPMP Database Schema
-- Version: 0.1.0
-- Purpose: Unified schema for project management across 11 domains
-- Architecture: Items (what) + Tasks (how) + Documents (supporting materials)
-- ============================================================================

-- Performance and reliability settings
PRAGMA journal_mode = WAL;              -- Write-Ahead Logging for concurrency
PRAGMA synchronous = NORMAL;            -- Balance safety and performance
PRAGMA busy_timeout = 5000;             -- 5 second wait on lock contention
PRAGMA foreign_keys = ON;               -- Enforce referential integrity
PRAGMA cache_size = -64000;             -- 64MB cache

-- ============================================================================
-- ITEMS: What we're building (the haystacks)
-- Supports 11 domains with flexible JSON attributes per domain
-- ============================================================================

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
        'project', 'milestone'
    )),
    
    domain TEXT NOT NULL CHECK (domain IN (
        'literature',      -- 9 books
        'janatpmp',        -- This platform
        'janat',           -- Core JANAT tech
        'atlas',           -- ATLAS architecture
        'meax',            -- MEAX framework
        'janatavern',      -- JanatAvern concepts
        'amphitheatre',    -- Troubadourian Amphitheatre
        'nexusweaver',     -- The Nexus Weaver platform
        'websites',        -- All 6 domains
        'social',          -- Social media presence
        'speaking',        -- Speaking engagements
        'life'             -- Personal life management
    )),
    
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
    -- Examples:
    --   Literature: {word_count, target_words, completion_percentage, manuscript_version}
    --   Code: {language, repo_url, test_coverage, dependencies[]}
    --   Websites: {domain_name, hosting, uptime_pct, traffic_monthly}
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
    completed_at TEXT
);

-- Generated virtual columns for indexable JSON fields
-- These allow efficient querying of JSON data without full table scans
ALTER TABLE items ADD COLUMN completion_pct REAL 
    GENERATED ALWAYS AS (CAST(json_extract(attributes, '$.completion_percentage') AS REAL)) VIRTUAL;

ALTER TABLE items ADD COLUMN word_count INTEGER 
    GENERATED ALWAYS AS (CAST(json_extract(attributes, '$.word_count') AS INTEGER)) VIRTUAL;

-- Indexes for common query patterns
CREATE INDEX idx_items_domain_status ON items(domain, status);
CREATE INDEX idx_items_type_updated ON items(entity_type, updated_at DESC);
CREATE INDEX idx_items_parent ON items(parent_id) WHERE parent_id IS NOT NULL;
CREATE INDEX idx_items_priority ON items(priority, status);
CREATE INDEX idx_items_due_date ON items(due_date) WHERE due_date IS NOT NULL AND status != 'completed';
CREATE INDEX idx_items_completion ON items(completion_pct) WHERE completion_pct IS NOT NULL;

-- Full-text search on items
CREATE VIRTUAL TABLE items_fts USING fts5(
    id UNINDEXED,
    entity_type UNINDEXED,
    domain UNINDEXED,
    title,
    description,
    tokenize = 'porter unicode61'
);

-- Trigger to keep FTS in sync
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

-- Auto-update timestamps
CREATE TRIGGER items_updated_at AFTER UPDATE ON items
BEGIN
    UPDATE items SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================================
-- TASKS: How we build things (the work queue)
-- Agent tasks, user stories, subtasks, reviews
-- ============================================================================

CREATE TABLE tasks (
    -- Core identification
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    
    -- Task classification
    task_type TEXT NOT NULL CHECK (task_type IN (
        'agent_story',     -- Delegated to agent (Antigravity/Gemini)
        'user_story',      -- Mat executes
        'subtask',         -- Decomposition of larger task
        'research',        -- Information gathering
        'review',          -- QA/testing
        'documentation'    -- Writing docs
    )),
    
    -- Assignment
    assigned_to TEXT CHECK (assigned_to IN (
        'agent',           -- Agentic IDE (Antigravity)
        'claude',          -- Claude assists
        'mat',             -- Mat executes
        'janus',           -- Future: Janus (Gemini consciousness)
        'unassigned'
    )) DEFAULT 'unassigned',
    
    -- What this task is building/modifying
    target_item_id TEXT REFERENCES items(id) ON DELETE CASCADE,
    
    -- Core attributes
    title TEXT NOT NULL,
    description TEXT,
    
    -- Work tracking
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending',
        'processing',
        'blocked',
        'review',
        'completed',
        'failed',
        'retry',
        'dlq'              -- Dead letter queue
    )),
    
    priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN (
        'urgent',
        'normal',
        'background'
    )),
    
    -- Agent-specific fields
    agent_instructions TEXT,           -- Detailed instructions for agent
    expected_output_schema JSON,       -- JSON schema for expected output
    
    -- Results
    output JSON,                        -- Agent/executor output
    confidence_score REAL,              -- Agent confidence (0.0-1.0)
    
    -- Retry configuration
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TEXT,
    
    -- Dependencies (array of task IDs this depends on)
    depends_on JSON DEFAULT '[]',
    
    -- Acceptance criteria
    acceptance_criteria TEXT,
    
    -- Resource tracking
    tokens_used INTEGER,
    cost_usd REAL,
    
    -- Temporal tracking
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for task management
CREATE INDEX idx_tasks_status ON tasks(status, priority);
CREATE INDEX idx_tasks_assigned ON tasks(assigned_to, status);
CREATE INDEX idx_tasks_target ON tasks(target_item_id) WHERE target_item_id IS NOT NULL;
CREATE INDEX idx_tasks_retry ON tasks(next_retry_at) WHERE status = 'retry';
CREATE INDEX idx_tasks_pending ON tasks(created_at) WHERE status = 'pending';

-- Auto-update timestamps
CREATE TRIGGER tasks_updated_at AFTER UPDATE ON tasks
BEGIN
    UPDATE tasks SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================================
-- DOCUMENTS: Supporting materials (the needles)
-- Conversations, files, artifacts, research, agent outputs
-- ============================================================================

CREATE TABLE documents (
    -- Core identification
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    
    -- Document classification
    doc_type TEXT NOT NULL CHECK (doc_type IN (
        'conversation',    -- From claude_exporter (603 conversations)
        'file',            -- User-uploaded file
        'artifact',        -- Generated artifact (code, docs, etc.)
        'research',        -- Research notes
        'agent_output',    -- Agent-generated content
        'session_notes',   -- Session minutes, journal entries
        'code'             -- Source code file
    )),
    
    -- Source tracking
    source TEXT NOT NULL CHECK (source IN (
        'claude_exporter', -- 603 conversations since Aug 2023
        'upload',          -- User upload
        'agent',           -- Agent generated
        'generated',       -- System generated
        'manual'           -- Manually created
    )),
    
    -- Core attributes
    title TEXT NOT NULL,
    
    -- Content (could be large)
    content TEXT,
    
    -- File metadata (if applicable)
    file_path TEXT,
    file_size INTEGER,
    mime_type TEXT,
    
    -- Conversation metadata (if applicable)
    conversation_uri TEXT,             -- From claude_exporter
    message_count INTEGER,
    token_count INTEGER,
    
    -- Vector embedding status
    embedding_status TEXT DEFAULT 'pending' CHECK (embedding_status IN (
        'pending',
        'processing',
        'completed',
        'failed'
    )),
    embedding_vector_id TEXT,          -- Reference to Qdrant
    
    -- Additional metadata
    metadata JSON NOT NULL DEFAULT '{}',
    
    -- Temporal tracking
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Indexes for document search and management
CREATE INDEX idx_documents_type ON documents(doc_type);
CREATE INDEX idx_documents_source ON documents(source);
CREATE INDEX idx_documents_embedding ON documents(embedding_status) WHERE embedding_status != 'completed';
CREATE INDEX idx_documents_conversation ON documents(conversation_uri) WHERE conversation_uri IS NOT NULL;
CREATE INDEX idx_documents_updated ON documents(updated_at DESC);

-- Full-text search on documents
CREATE VIRTUAL TABLE documents_fts USING fts5(
    id UNINDEXED,
    doc_type UNINDEXED,
    title,
    content,
    tokenize = 'porter unicode61'
);

-- Trigger to keep FTS in sync
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

-- Auto-update timestamps
CREATE TRIGGER documents_updated_at AFTER UPDATE ON documents
BEGIN
    UPDATE documents SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================================
-- RELATIONSHIPS: Universal connector
-- Links items to items, items to tasks, documents to anything, etc.
-- ============================================================================

CREATE TABLE relationships (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    
    -- Source and target (generic references)
    source_type TEXT NOT NULL CHECK (source_type IN ('item', 'task', 'document')),
    source_id TEXT NOT NULL,
    
    target_type TEXT NOT NULL CHECK (target_type IN ('item', 'task', 'document')),
    target_id TEXT NOT NULL,
    
    -- Relationship semantics
    relationship_type TEXT NOT NULL CHECK (relationship_type IN (
        'blocks',          -- Source blocks target
        'enables',         -- Source enables target
        'informs',         -- Source informs/supports target
        'references',      -- Source references target
        'implements',      -- Source implements target
        'documents',       -- Source documents target
        'depends_on',      -- Source depends on target
        'parent_of',       -- Source is parent of target
        'attached_to'      -- Source is attached to target
    )),
    
    -- Strength (for prioritization/filtering)
    strength TEXT DEFAULT 'hard' CHECK (strength IN ('hard', 'soft')),
    
    -- Additional metadata
    metadata JSON DEFAULT '{}',
    
    -- Temporal tracking
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    
    -- Prevent duplicate relationships
    UNIQUE(source_type, source_id, target_type, target_id, relationship_type)
);

-- Indexes for relationship traversal
CREATE INDEX idx_relationships_source ON relationships(source_type, source_id);
CREATE INDEX idx_relationships_target ON relationships(target_type, target_id);
CREATE INDEX idx_relationships_type ON relationships(relationship_type);

-- ============================================================================
-- CDC OUTBOX: Change Data Capture for eventual consistency
-- Enables sync to Qdrant (vector) and Neo4j (graph) when needed
-- ============================================================================

CREATE TABLE cdc_outbox (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    
    -- What changed
    operation TEXT NOT NULL CHECK (operation IN ('INSERT', 'UPDATE', 'DELETE')),
    entity_type TEXT NOT NULL CHECK (entity_type IN ('item', 'task', 'document', 'relationship')),
    entity_id TEXT NOT NULL,
    
    -- Change payload (JSON snapshot of the entity)
    payload JSON NOT NULL,
    
    -- Sync status to downstream systems
    processed_qdrant INTEGER DEFAULT 0,     -- 0 = pending, 1 = synced
    processed_neo4j INTEGER DEFAULT 0,      -- 0 = pending, 1 = synced
    
    -- Temporal tracking
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

-- Index for finding pending sync operations
CREATE INDEX idx_cdc_pending_qdrant ON cdc_outbox(processed_qdrant, created_at) WHERE processed_qdrant = 0;
CREATE INDEX idx_cdc_pending_neo4j ON cdc_outbox(processed_neo4j, created_at) WHERE processed_neo4j = 0;

-- Triggers to populate CDC outbox on changes

-- Items CDC
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

-- ============================================================================
-- SCHEMA VERSION TRACKING
-- ============================================================================

CREATE TABLE schema_version (
    version TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT
);

INSERT INTO schema_version (version, description) VALUES
    ('0.1.0', 'Initial schema: Items, Tasks, Documents, Relationships, CDC Outbox');
