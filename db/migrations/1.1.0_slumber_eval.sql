-- Migration 1.1.0: Slumber evaluation metadata for R22 First Light
-- Stores per-turn evaluation rationale, emotional register, and
-- provider/model that performed the evaluation.

ALTER TABLE messages_metadata ADD COLUMN eval_rationale TEXT DEFAULT '';
ALTER TABLE messages_metadata ADD COLUMN eval_emotional_register TEXT DEFAULT '';
ALTER TABLE messages_metadata ADD COLUMN eval_provider TEXT DEFAULT '';
ALTER TABLE messages_metadata ADD COLUMN eval_model TEXT DEFAULT '';

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('1.1.0', 'R22: Slumber evaluation metadata');
