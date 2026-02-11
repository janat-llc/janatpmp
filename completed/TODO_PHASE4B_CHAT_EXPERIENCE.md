# Phase 4B: Chat Experience Redesign

**Status:** Architecture complete — ready for implementation  
**Reference:** Google AI Studio three-panel layout  
**Architect:** Claude + Mat (Feb 10, 2026)  
**Implementor:** Agent (Antigravity/Gemini)

---

## Vision

Transform the Chat tab from a basic chatbot widget into a proper AI conversation
interface modeled after Google AI Studio. Three-panel layout: chat history (left),
conversation (center), model settings (right). All conversations persist with a
triplet schema designed for future fine-tuning extraction.

---

## Architecture Decisions

### AD-1: Triplet Message Schema
Every conversation turn stores THREE distinct artifacts:
- `user_prompt` — what was asked
- `model_reasoning` — chain-of-thought / thinking tokens (e.g. `<think>` blocks)
- `model_response` — the visible reply

**Why:** Enables fine-tuning Nemotron on its own reasoning patterns. We can extract
prompt→reasoning pairs, reasoning→response pairs, or full triplets for different
training objectives. This is a training data pipeline disguised as a chat UI.

### AD-2: Three-Panel Layout (AI Studio Pattern)
| Panel | Content | Implementation |
|-------|---------|---------------|
| Left sidebar | Chat history list, "New Chat", search | `gr.Sidebar(position="left")` — render conditionally when `active_tab == "Chat"` |
| Center | Chatbot, input (Enter=send), tool chips | Main tab content area |
| Right sidebar | Provider, model, temperature, top_p, system prompt append, tool toggles | `gr.Sidebar(position="right")` — render conditionally when `active_tab == "Chat"` |

When NOT on Chat tab:
- Left sidebar = current contextual sidebar (projects, tasks, etc.)
- Right sidebar = current Claude quick-chat

### AD-3: System Prompt Layering
- **Base system prompt** lives in Admin settings (platform context, tool descriptions)
- **Session append** lives per-conversation (scoping to a project, persona, etc.)
- At inference time: `base_prompt + "\n\n" + session_append`

### AD-4: "New Chat" Not "Clear Chat"
"New Chat" button behavior:
1. Verify current conversation's last message is persisted to DB
2. Create new conversation record
3. Clear the chatbot display
4. Set the new conversation as active

### AD-5: Auto-Title from First Prompt
- On first user message, auto-generate title (first 50 chars of prompt, or ask model to summarize)
- Title is editable in the history sidebar (click to rename in left sidebar)

### AD-8: Conversation Sources — Not Just Platform Chats
Conversations table holds ALL conversation history, not just chats originating in the platform:
- `source = 'platform'` — chats created in the Chat tab
- `source = 'claude_export'` — 600+ conversations imported from Claude Export
- `source = 'imported'` — conversations from other sources (Gemini, etc.)

Any conversation, regardless of source, can be loaded into the Chat UI and discussed
with whatever provider/model is selected. Claude Export conversations are primarily
for RAG, but they should be browsable and loadable too.

This means the Claude Export ingestion pipeline (`services/claude_export.py`) needs
a new pathway: in addition to creating `documents` records, it should create
`conversations` + `messages` records. The existing documents pipeline stays as-is
for backward compatibility.

### AD-9: Tool Routing (Future — Don't Solve Now, Don't Block)
Some tool calls should route to local models (Nemotron), others to Claude (via MCP
in Claude Code/Desktop), others to Gemini. This is complex and will be its own phase.

For now, the schema captures enough to support future routing:
- `tools_called` JSON array on each message tracks which tools were used
- `provider` + `model` per-turn snapshots what answered
- Tool toggles in the UI control what's available per-session

MCP tools are already exposed to Claude Code and Claude Desktop. The routing
layer will sit between the Chat UI and the provider backends when we build it.

### AD-6: Reasoning Extraction on Ingest
When model response contains `<think>...</think>` blocks (deepseek-r1, nemotron reasoning):
- Parse thinking tokens OUT of response
- Store in `model_reasoning` column
- Store clean response in `model_response`
- This keeps triplets clean from the start (no post-processing needed for fine-tuning export)

### AD-7: Input UX
- Enter = send message
- Shift+Enter = newline
- No send button, no clear button (reduces clutter)
- Gradio Textbox with `max_lines=5` and `submit_btn=False` (or just wire `.submit`)

---

## Schema Changes

Add to `db/schema.sql` (and create migration `db/migrations/0.3.0_conversations.sql`):

```sql
-- ============================================================================
-- CONVERSATIONS: Chat sessions with context
-- ============================================================================

CREATE TABLE conversations (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    title TEXT NOT NULL DEFAULT 'New Chat',
    
    -- Source tracking
    source TEXT NOT NULL DEFAULT 'platform' CHECK (source IN (
        'platform',        -- Created in Chat tab
        'claude_export',   -- Imported from Claude Export (600+ conversations)
        'imported'          -- From other sources (Gemini, etc.)
    )),
    
    provider TEXT NOT NULL DEFAULT 'ollama',
    model TEXT NOT NULL DEFAULT 'nemotron-3-nano:latest',
    
    -- System prompt scoping for this session (appended to base from Admin)
    system_prompt_append TEXT DEFAULT '',
    
    -- Model parameters snapshot
    temperature REAL DEFAULT 0.7,
    top_p REAL DEFAULT 0.9,
    max_tokens INTEGER DEFAULT 2048,
    
    -- Status
    is_active INTEGER DEFAULT 1,          -- 1 = visible, 0 = archived
    message_count INTEGER DEFAULT 0,
    
    -- Source reference (for claude_export linkage)
    conversation_uri TEXT,                -- Claude Export URI if applicable
    
    -- Temporal tracking
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_conversations_active ON conversations(is_active, updated_at DESC);
CREATE INDEX idx_conversations_source ON conversations(source, updated_at DESC);
CREATE INDEX idx_conversations_provider ON conversations(provider);

-- Auto-update timestamps
CREATE TRIGGER conversations_updated_at AFTER UPDATE ON conversations
BEGIN
    UPDATE conversations SET updated_at = datetime('now') WHERE id = NEW.id;
END;

-- ============================================================================
-- MESSAGES: Triplet storage (prompt + reasoning + response)
-- Designed for fine-tuning data extraction
-- ============================================================================

CREATE TABLE messages (
    id TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16)))),
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    sequence INTEGER NOT NULL,              -- turn order (1, 2, 3...)
    
    -- The triplet
    user_prompt TEXT NOT NULL,
    model_reasoning TEXT DEFAULT '',         -- CoT / thinking tokens
    model_response TEXT NOT NULL DEFAULT '',
    
    -- Snapshot of what model answered this turn
    provider TEXT,
    model TEXT,
    
    -- Token accounting (for cost tracking and fine-tuning dataset sizing)
    tokens_prompt INTEGER DEFAULT 0,
    tokens_reasoning INTEGER DEFAULT 0,
    tokens_response INTEGER DEFAULT 0,
    
    -- Tool usage tracking
    tools_called JSON DEFAULT '[]',         -- array of tool names used this turn
    
    -- Temporal tracking
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, sequence);
CREATE INDEX idx_messages_created ON messages(created_at DESC);

-- FTS on messages for searching across conversations
CREATE VIRTUAL TABLE messages_fts USING fts5(
    id UNINDEXED,
    conversation_id UNINDEXED,
    user_prompt,
    model_response,
    tokenize = 'porter unicode61'
);

CREATE TRIGGER messages_fts_insert AFTER INSERT ON messages
BEGIN
    INSERT INTO messages_fts(id, conversation_id, user_prompt, model_response)
    VALUES (NEW.id, NEW.conversation_id, NEW.user_prompt, NEW.model_response);
END;

CREATE TRIGGER messages_fts_delete AFTER DELETE ON messages
BEGIN
    DELETE FROM messages_fts WHERE id = OLD.id;
END;

-- Update conversation message_count on insert
CREATE TRIGGER messages_count_insert AFTER INSERT ON messages
BEGIN
    UPDATE conversations 
    SET message_count = message_count + 1, updated_at = datetime('now')
    WHERE id = NEW.conversation_id;
END;

-- CDC triggers for conversations and messages
CREATE TRIGGER cdc_conversations_insert AFTER INSERT ON conversations
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'conversation', NEW.id, json_object(
        'id', NEW.id, 'title', NEW.title, 'provider', NEW.provider, 'model', NEW.model
    ));
END;

CREATE TRIGGER cdc_messages_insert AFTER INSERT ON messages
BEGIN
    INSERT INTO cdc_outbox (operation, entity_type, entity_id, payload)
    VALUES ('INSERT', 'message', NEW.id, json_object(
        'id', NEW.id, 'conversation_id', NEW.conversation_id,
        'user_prompt', NEW.user_prompt, 'model_response', NEW.model_response
    ));
END;

-- Update relationship types to include 'conversation' entity
-- (handled via relationships table — source_type/target_type need 'conversation' added)

INSERT OR IGNORE INTO schema_version (version, description) VALUES
    ('0.3.0', 'Add conversations and messages tables with triplet schema');
```

**IMPORTANT:** The `relationships` table CHECK constraint on `source_type` and `target_type` 
currently only allows `('item', 'task', 'document')`. A migration must add `'conversation'`
and `'message'` to these constraints so conversations can be linked to items/projects.

---

## Database Operations

Add to `db/operations.py` (or create `db/chat_operations.py`):

### Conversation CRUD
```python
def create_conversation(provider, model, system_prompt_append="", temperature=0.7, top_p=0.9) -> str
def get_conversation(conversation_id) -> dict
def list_conversations(limit=50, active_only=True) -> list[dict]
def update_conversation(conversation_id, **kwargs) -> None  # title, system_prompt_append, is_active
def delete_conversation(conversation_id) -> None
def search_conversations(query) -> list[dict]  # FTS across messages
```

### Message CRUD
```python
def add_message(conversation_id, user_prompt, model_reasoning, model_response, provider, model, tokens_prompt=0, tokens_reasoning=0, tokens_response=0, tools_called=None) -> str
def get_messages(conversation_id, limit=100) -> list[dict]  # ordered by sequence
def get_next_sequence(conversation_id) -> int
```

### Reasoning Parser
```python
def parse_reasoning(raw_response: str) -> tuple[str, str]:
    """
    Extract reasoning from model response.
    Returns (reasoning, clean_response).
    
    Handles:
    - <think>...</think> blocks (deepseek-r1)
    - <reasoning>...</reasoning> blocks
    - Future: other CoT formats
    """
```

---

## MCP Tool Exposure

Add these as MCP-accessible tools in `services/mcp_server.py` (or however tools are exposed):

```
- create_conversation
- list_conversations  
- get_conversation
- add_message
- get_messages
- search_conversations
```

This allows Claude (via MCP) to create and search conversations from external tools.

---

## UI Changes

### File: `pages/projects.py`

#### Chat Tab Center (replace current layout)
```python
with gr.Tab("Chat") as chat_tab:
    chat_tab_chatbot = gr.Chatbot(
        value=[],
        height=600,
        label="Chat",
        show_copy_button=True,    # copy individual messages
    )
    chat_tab_input = gr.Textbox(
        placeholder="Ask anything... (Enter to send, Shift+Enter for newline)",
        show_label=False,
        interactive=True,
        max_lines=5,
        autofocus=True,
    )
    # No send button, no clear button — Enter sends
```

#### Left Sidebar — Chat History (when tab == "Chat")
Inside `render_left`, replace the Chat section with:
```python
elif tab == "Chat":
    gr.Markdown("### Conversations")
    new_chat_btn = gr.Button("+ New Chat", variant="primary", size="sm")
    
    # Load conversation list from DB
    conversations = list_conversations(limit=30)
    
    for conv in conversations:
        # Truncated title, click to load
        conv_btn = gr.Button(
            conv['title'][:40],
            variant="secondary" if conv['id'] != active_conversation_id else "primary",
            size="sm",
            key=f"conv-{conv['id']}",
        )
        conv_btn.click(...)  # load conversation into chatbot
    
    if conversations:
        gr.Markdown("---")
        gr.Button("View all history →", size="sm")
```

#### Right Sidebar — Chat Settings (when tab == "Chat")
The right sidebar currently always shows Claude chat. Make it conditional:
```python
with gr.Sidebar(position="right"):
    @gr.render(inputs=[active_tab, ...])
    def render_right(tab, ...):
        if tab == "Chat":
            gr.Markdown("### Chat Settings")
            # Provider dropdown
            # Model dropdown  
            # Temperature slider (0.0 - 2.0, default 0.7)
            # Top P slider (0.0 - 1.0, default 0.9)
            # Max tokens slider (256 - 8192, default 2048)
            # System prompt append textbox
            # Tool toggles (checkboxes)
            gr.Markdown("---")
            gr.Markdown("### Tools")
            gr.CheckboxGroup(
                ["DB Search", "DB Write", "Web Search"],
                value=["DB Search"],
                label="Enabled Tools",
            )
        else:
            # Original Claude quick-chat sidebar
            gr.Markdown("### Claude")
            # ... existing sidebar chat code ...
```

**CRITICAL:** All event listeners for components created inside `@gr.render` 
MUST be defined inside the same render function. Use State variables to bridge
data out to the main wiring section.

---

## State Variables Needed

```python
active_conversation_id = gr.State("")        # current conversation ID
chat_tab_history = gr.State([])              # chatbot display messages
chat_tab_provider_state = gr.State("ollama")
chat_tab_model_state = gr.State("nemotron-3-nano:latest")
chat_tab_temperature = gr.State(0.7)
chat_tab_top_p = gr.State(0.9)
chat_tab_max_tokens = gr.State(2048)
chat_tab_system_append = gr.State("")
```

---

## Chat Flow (Updated)

1. User types message, presses Enter
2. Message appended to chatbot display immediately (optimistic UI)
3. `_handle_chat_tab()` fires:
   a. If no active conversation, create one → set `active_conversation_id`
   b. Auto-title from first prompt (first 50 chars)
   c. Build system prompt: `base_from_admin + "\n\n" + session_append`
   d. Temp-override settings for provider/model
   e. Call `chat()` with full history
   f. Parse reasoning from response
   g. Store triplet in DB via `add_message()`
   h. Restore original settings
   i. Update chatbot display with clean response
   j. Update conversation list in left sidebar

---

## Implementation Order (Agent Tasks)

### Task 1: Schema Migration
- [ ] Create `db/migrations/0.3.0_conversations.sql` with conversations + messages tables
- [ ] Update `db/schema.sql` to include new tables
- [ ] Add migration runner to `app.py` startup (or manual apply)
- [ ] Update `relationships` CHECK constraints to allow 'conversation' and 'message'

### Task 2: Database Operations  
- [ ] Create `db/chat_operations.py` with all CRUD functions listed above
- [ ] Add `parse_reasoning()` helper function
- [ ] Add FTS search across messages
- [ ] Write basic tests

### Task 3: MCP Tool Exposure
- [ ] Expose conversation/message operations as MCP tools
- [ ] Test via Claude MCP integration

### Task 4: Chat Tab UI Rebuild
- [ ] Replace Chat tab center with clean layout (chatbot + input, no buttons)
- [ ] Make right sidebar conditional (chat settings when on Chat tab, Claude chat otherwise)
- [ ] Update left sidebar Chat section with conversation history list
- [ ] Wire all State variables

### Task 5: Chat Handler Update
- [ ] Update `_handle_chat_tab()` for conversation persistence flow
- [ ] Integrate `parse_reasoning()` into response processing
- [ ] Add "New Chat" flow (verify save → create new → clear display)
- [ ] Add "Load Conversation" flow (click history item → load messages → display)

### Task 6: Settings Integration
- [ ] Add temperature, top_p, max_tokens to chat API calls
- [ ] System prompt layering (base + append)
- [ ] Tool toggles that control which tools are available per-session

---

## Files to Modify

| File | Changes |
|------|---------|
| `db/schema.sql` | Add conversations + messages tables |
| `db/migrations/0.3.0_conversations.sql` | Migration script |
| `db/chat_operations.py` | NEW — conversation/message CRUD |
| `db/operations.py` | Update relationship constraints |
| `services/chat.py` | Accept temperature/top_p/max_tokens params, parse reasoning |
| `pages/projects.py` | Chat tab rebuild, right sidebar conditional, state wiring |
| `CLAUDE.md` | Update status and architecture docs |

---

## What NOT To Change
- Admin tab system prompt editor (already works, becomes "base prompt")
- Sidebar Claude chat behavior on non-Chat tabs (stays as-is)
- Existing Items/Tasks/Documents schema (untouched)
- MCP tool exposure for existing operations (untouched)

---

## Reference: Google AI Studio Layout
- Left: Conversation history (clickable, searchable)
- Center: Chat window with input at bottom
- Right: Run settings (model, temperature, thinking level, tools, system instructions)
- Input: "Start typing a prompt, use alt+enter to append" (we use Shift+Enter)
