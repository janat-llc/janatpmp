-- Migration 2.0.0: True salience scoring for HF-01 Salience Calibration
-- Adds dedicated salience_score column distinct from quality_score.
-- quality_score = response quality (helpfulness, coherence)
-- salience_score = memory importance to Janus and the Janat Initiative

ALTER TABLE messages_metadata ADD COLUMN salience_score REAL;
ALTER TABLE messages_metadata ADD COLUMN salience_reasoning TEXT DEFAULT '';

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('2.0.0', 'HF-01: True salience scoring — salience_score distinct from quality_score');
