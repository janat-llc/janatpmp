-- ============================================================================
-- Migration 0.7.0: Pipeline observability columns on messages_metadata
-- Stores system prompt length, RAG context text, and synthesis flag per turn.
-- ============================================================================

ALTER TABLE messages_metadata ADD COLUMN system_prompt_length INTEGER;
ALTER TABLE messages_metadata ADD COLUMN rag_context_text TEXT;
ALTER TABLE messages_metadata ADD COLUMN rag_synthesized INTEGER DEFAULT 0;

INSERT OR IGNORE INTO schema_version (version, description) VALUES
    ('0.7.0', 'Pipeline observability — system prompt length, RAG context, synthesis flag');
