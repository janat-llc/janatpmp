-- ============================================================================
-- Migration 0.4.1: Add missing FTS UPDATE trigger on messages table
-- ============================================================================
-- The 0.3.0 migration created INSERT and DELETE triggers for messages_fts
-- but omitted the UPDATE trigger. Edits to messages didn't sync to the FTS
-- index, making edited content unsearchable.

CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages
BEGIN
    DELETE FROM messages_fts WHERE id = OLD.id;
    INSERT INTO messages_fts(id, conversation_id, user_prompt, model_response)
    VALUES (NEW.id, NEW.conversation_id, NEW.user_prompt, NEW.model_response);
END;

INSERT OR IGNORE INTO schema_version (version, description) VALUES
    ('0.4.1', 'Add missing FTS UPDATE trigger on messages table');
