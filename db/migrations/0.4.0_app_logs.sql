-- ============================================================================
-- Migration 0.4.0: Add app_logs table for centralized application logging
-- ============================================================================

CREATE TABLE IF NOT EXISTS app_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    level TEXT NOT NULL,
    module TEXT NOT NULL,
    function TEXT DEFAULT '',
    message TEXT NOT NULL,
    metadata JSON DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'utc'))
);

CREATE INDEX IF NOT EXISTS idx_logs_level_ts ON app_logs(level, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_logs_module ON app_logs(module, timestamp DESC);

INSERT OR IGNORE INTO schema_version (version, description) VALUES
    ('0.4.0', 'Add app_logs table for centralized application logging');
