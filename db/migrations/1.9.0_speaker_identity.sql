-- Migration 1.9.0: Speaker identity on messages (R39)
-- Tracks who is speaking: mat, claude, agent, etc.

ALTER TABLE messages ADD COLUMN speaker TEXT NOT NULL DEFAULT 'mat';

INSERT INTO schema_version (version, description)
VALUES ('1.9.0', 'Speaker identity: speaker column on messages');
