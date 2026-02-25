-- Migration 1.0.0: Cognition trace columns for R21 Strange Loop
-- Stores per-turn prompt layer breakdown and graph ranking trace
-- in messages_metadata for the Cognition Tab and future Slumber analysis.

ALTER TABLE messages_metadata ADD COLUMN cognition_prompt_layers TEXT DEFAULT '';
ALTER TABLE messages_metadata ADD COLUMN cognition_graph_trace TEXT DEFAULT '';

INSERT OR IGNORE INTO schema_version (version) VALUES ('1.0.0');
