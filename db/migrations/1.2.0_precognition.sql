-- Migration 1.2.0: Pre-cognition trace column for R25
-- Stores the full pre-cognition result (signals, directives, weights, latency)

ALTER TABLE messages_metadata ADD COLUMN cognition_precognition TEXT DEFAULT '';

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('1.2.0', 'R25: Pre-cognition trace metadata');
