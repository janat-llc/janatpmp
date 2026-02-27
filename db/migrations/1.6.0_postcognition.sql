-- Migration 1.6.0: Post-cognition corrective signal (R33)
-- Stores the full post-cognition evaluation result per-message.

ALTER TABLE messages_metadata ADD COLUMN cognition_postcognition TEXT DEFAULT '';

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('1.6.0', 'R33: Post-cognition corrective signal');
