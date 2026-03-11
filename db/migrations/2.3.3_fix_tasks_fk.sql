-- Migration 2.3.3: Fix tasks.target_item_id foreign key (R57)
-- tasks.target_item_id references "items_backup"(id) — a ghost from migration 2.2.0
-- which renamed items→items_backup then created new items but left the FK broken.
-- SQLite has no ALTER TABLE MODIFY COLUMN — full table recreation required.

PRAGMA foreign_keys=OFF;

-- Step 1: Rename existing table
ALTER TABLE tasks RENAME TO tasks_old;

-- Step 2: Drop triggers that reference tasks
DROP TRIGGER IF EXISTS tasks_updated_at;
DROP TRIGGER IF EXISTS cdc_tasks_insert;
DROP TRIGGER IF EXISTS cdc_tasks_update;
DROP TRIGGER IF EXISTS cdc_tasks_delete;

-- Step 3: Recreate tasks with corrected foreign key (items, not items_backup)
CREATE TABLE tasks (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    task_type TEXT NOT NULL CHECK (task_type IN (
        'agent_story',
        'user_story',
        'subtask',
        'research',
        'review',
        'documentation'
    )),
    assigned_to TEXT CHECK (assigned_to IN (
        'agent',
        'claude',
        'mat',
        'janus',
        'unassigned'
    )) DEFAULT 'unassigned',
    target_item_id TEXT REFERENCES items(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending',
        'processing',
        'blocked',
        'review',
        'completed',
        'failed',
        'retry',
        'dlq'
    )),
    priority TEXT NOT NULL DEFAULT 'normal' CHECK (priority IN (
        'urgent',
        'normal',
        'background'
    )),
    agent_instructions TEXT,
    expected_output_schema JSON,
    output JSON,
    confidence_score REAL,
    retry_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    next_retry_at TEXT,
    depends_on JSON DEFAULT '[]',
    acceptance_criteria TEXT,
    tokens_used INTEGER,
    cost_usd REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    started_at TEXT,
    completed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    created_by TEXT NOT NULL DEFAULT 'unknown',
    modified_by TEXT NOT NULL DEFAULT 'unknown'
);

-- Step 4: Copy all existing tasks
INSERT INTO tasks SELECT * FROM tasks_old;
DROP TABLE tasks_old;

-- Step 5: Recreate triggers
CREATE TRIGGER tasks_updated_at AFTER UPDATE ON tasks
BEGIN
    UPDATE tasks SET updated_at = datetime('now') WHERE id = NEW.id;
END;

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

PRAGMA foreign_keys=ON;

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('2.3.3', 'Fix tasks.target_item_id FK — items_backup → items');
