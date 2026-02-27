-- 1.4.0: Entity salience column (R31: The Web)
-- SQLite is source of truth for entity salience; Qdrant payload is the search index.
-- If Qdrant collections are recreated, salience can be re-propagated from this column.
ALTER TABLE entities ADD COLUMN salience REAL DEFAULT 0.5;

INSERT OR IGNORE INTO schema_version (version, description)
VALUES ('1.4.0', 'Entity salience column (R31: The Web)');
