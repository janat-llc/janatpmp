-- 1.5.0: Register exemplars table (R32: The Mirror)
-- Stores conversational register evaluations mined by Slumber.
-- SQLite is source of truth; Qdrant embedding is the search index.
CREATE TABLE IF NOT EXISTS register_exemplars (
    id TEXT PRIMARY KEY DEFAULT (hex(randomblob(16))),
    message_id TEXT NOT NULL REFERENCES messages(id),
    register_label TEXT NOT NULL,        -- 'warm', 'neutral', 'clinical'
    register_score REAL,                 -- 0.0-1.0 warmth score
    rationale TEXT,                      -- Evaluator reasoning
    authentic_phrases TEXT DEFAULT '[]', -- JSON array of genuine phrases
    performed_phrases TEXT DEFAULT '[]', -- JSON array of robotic phrases
    topics TEXT DEFAULT '[]',            -- JSON array of topic tags
    evaluator_model TEXT,
    evaluated_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_register_exemplars_score
    ON register_exemplars(register_score DESC);
CREATE INDEX IF NOT EXISTS idx_register_exemplars_label
    ON register_exemplars(register_label);

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('1.5.0', 'Register exemplars table (R32: The Mirror)');
