-- Migration 1.7.0: Add role column to messages (R35)
--
-- Existing messages get role='turn' (standard user/assistant triplets).
-- New system messages use role='system/intent', 'system/precognition', etc.
-- The role column is TEXT with no constraint — new role values just work.

ALTER TABLE messages ADD COLUMN role TEXT DEFAULT 'turn';

INSERT INTO schema_version (version) VALUES ('1.7.0');
