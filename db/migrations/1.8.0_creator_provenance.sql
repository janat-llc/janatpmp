-- Migration 1.8.0: Creator Provenance (R38)
-- Add created_by and modified_by columns to items, tasks, documents

-- Items
ALTER TABLE items ADD COLUMN created_by TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE items ADD COLUMN modified_by TEXT NOT NULL DEFAULT 'unknown';

-- Tasks
ALTER TABLE tasks ADD COLUMN created_by TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE tasks ADD COLUMN modified_by TEXT NOT NULL DEFAULT 'unknown';

-- Documents
ALTER TABLE documents ADD COLUMN created_by TEXT NOT NULL DEFAULT 'unknown';
ALTER TABLE documents ADD COLUMN modified_by TEXT NOT NULL DEFAULT 'unknown';

-- Version stamp
INSERT INTO schema_version (version, description)
VALUES ('1.8.0', 'Creator provenance: created_by + modified_by on items, tasks, documents');
