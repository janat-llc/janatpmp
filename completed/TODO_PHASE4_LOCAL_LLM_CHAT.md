# Phase 4: Local LLM Integration + Chat Tab

## Overview

Connect JANATPMP to a local Ollama instance for local-first LLM inference.
Add a dedicated Chat tab as a 5th top-level tab for full-width conversations.
Prepare for NVIDIA Nemotron Reasoning Challenge (Feb 19 - Apr 15).

**Priority:** Get local inference working end-to-end before Nemotron challenge (Feb 19).

## Docker Architecture Change

Ollama is now a service in JANATPMP's own docker-compose.yml.

- **Container:** `janatpmp-ollama` (separate from janatopenwebui's `ollama`)
- **Port:** `11435:11434` on host (avoids conflict with janatopenwebui's `11434:11434`)
- **Volume:** `ollama_data` (external) — same models shared with janatopenwebui stack
- **Network:** `janatpmp_network` — JANATPMP reaches Ollama at `http://ollama:11434/v1`
- **GPU:** Full NVIDIA passthrough

Both Ollama containers can run simultaneously since they have different host ports
and different container names. They share the same model volume.

## Prerequisites (Mat does these manually)

### P1: Pull latest Ollama image

```powershell
docker pull ollama/ollama:latest
```

### P2: Rebuild and start JANATPMP stack

```powershell
cd C:\Janat\JANATPMP
docker compose down
docker compose up -d --build
```

This starts both `janatpmp` and `janatpmp-ollama`.

### P3: Pull nemotron-3-nano

```powershell
docker exec janatpmp-ollama ollama pull nemotron-3-nano
```

### P4: Verify Ollama is serving

```powershell
# From host (port 11435)
curl http://localhost:11435/v1/models

# From inside janatpmp container (port 11434 via network)
docker exec janatpmp-core curl http://ollama:11434/v1/models
```

**Mat does P1-P4.** Everything below is agent work.

---

## Files Changed

| File | Action |
|------|--------|
| `docker-compose.yml` | ✅ DONE — Ollama service added |
| `services/settings.py` | ✅ DONE — base_url default → `http://ollama:11434/v1` |
| `services/chat.py` | ✅ DONE — Ollama presets with Mat's actual models |
| `pages/projects.py` | ✅ DONE — Chat tab, state, wiring, sidebar, tab tracking |
| `CLAUDE.md` | ✅ DONE — Phase 4 status, 5-tab table, Docker/Ollama docs |
| `docs/TODO_PHASE4_LOCAL_LLM_CHAT.md` | This file |

## Files NOT Changed

- `db/schema.sql` — NO schema changes
- `db/operations.py` — NO changes
- `app.py` — NO changes
- `requirements.txt` — NO changes (openai package already present)
- `Dockerfile` — NO changes
- No new dependencies

---

## Task 1: Fix Ollama Base URL Default

**File:** `services/settings.py`

**What:** Change default base_url from `http://localhost:11434/v1` to
`http://ollama:11434/v1`. This uses Docker's internal DNS since both
containers share `janatpmp_network`.

In the `DEFAULTS` dict, find and update the `chat_base_url` entry:

```python
"chat_base_url": ("http://ollama:11434/v1", False),
```

---

## Task 2: Update Ollama Model Presets

**File:** `services/chat.py`

In the `PROVIDER_PRESETS` dict, update the `ollama` entry:

```python
"ollama": {
    "name": "Ollama (Local)",
    "models": [
        "nemotron-3-nano:latest",
        "deepseek-r1:7b-qwen-distill-q4_K_M",
        "deepseek-r1:latest",
        "qwen3:4b-instruct-2507-q4_K_M",
        "phi4-mini-reasoning:latest",
    ],
    "default_model": "nemotron-3-nano:latest",
    "needs_api_key": False,
    "base_url": "http://ollama:11434/v1",
},
```

These match the models Mat has pulled locally. `nemotron-3-nano` is the default
since that's the target for the NVIDIA challenge.

---

## Task 3: Add Chat Tab

**File:** `pages/projects.py`

### 3a. Add import at top of file

```python
from services.chat import PROVIDER_PRESETS
```

### 3b. Add Chat tab as the 5th top-level tab

Insert AFTER the Knowledge tab block and BEFORE the Admin tab block.
This goes inside the existing `with gr.Tabs():` block.

```python
        # --- Chat tab ---
        with gr.Tab("Chat") as chat_tab:
            with gr.Row():
                with gr.Column(scale=3):
                    chat_tab_chatbot = gr.Chatbot(
                        value=list(INITIAL_CHAT),
                        height=550,
                        label="Chat",
                    )
                    with gr.Row():
                        chat_tab_input = gr.Textbox(
                            placeholder="Ask anything...",
                            show_label=False,
                            interactive=True,
                            max_lines=3,
                            scale=6,
                        )
                        chat_tab_send = gr.Button(
                            "Send", variant="primary", scale=1,
                        )
                    with gr.Row():
                        chat_tab_clear = gr.Button("Clear Chat", size="sm")

                with gr.Column(scale=1):
                    gr.Markdown("### Model")
                    chat_tab_provider = gr.Dropdown(
                        choices=["anthropic", "gemini", "ollama"],
                        value="ollama",
                        label="Provider",
                        interactive=True,
                    )
                    chat_tab_model = gr.Dropdown(
                        choices=PROVIDER_PRESETS.get("ollama", {}).get("models", []),
                        value=PROVIDER_PRESETS.get("ollama", {}).get("default_model", ""),
                        label="Model",
                        interactive=True,
                        allow_custom_value=True,
                    )
                    chat_tab_status = gr.Markdown("*Ready*")
                    gr.Markdown("---")
                    gr.Markdown(
                        "**Tip:** This tab uses its own provider/model "
                        "selection independent of the sidebar chat. "
                        "Switch to Ollama for local inference."
                    )
```

### 3c. Add Chat tab state

In the `# === STATES ===` section, add:

```python
    chat_tab_history = gr.State(list(INITIAL_CHAT))
```

### 3d. Add tab tracking

In the `# === TAB TRACKING ===` section, add:

```python
    chat_tab.select(lambda: "Chat", outputs=[active_tab], api_visibility="private")
```

### 3e. Add Chat tab to left sidebar render

In the `render_left` function, add an `elif tab == "Chat":` block after
the Knowledge block and before the Admin block:

```python
            elif tab == "Chat":
                gr.Markdown("### Chat")
                gr.Markdown(
                    "Full conversation interface.\n\n"
                    "Use the panel on the right to select "
                    "your provider and model.\n\n"
                    "The sidebar chat (right) is for quick "
                    "DB operations on any tab. This tab is "
                    "for longer conversations."
                )
```

### 3f. Chat tab event wiring

Add a new section `# === CHAT TAB WIRING ===` after the existing
`# === CHAT WIRING ===` section:

```python
    # === CHAT TAB WIRING ===

    def _chat_tab_send(message, history, provider, model):
        """Send message using the Chat tab's own provider/model selection."""
        if not message.strip():
            return history, history, "", "*Ready*"
        from services.chat import chat as _chat_fn
        from services.settings import get_setting, set_setting

        # Temporarily override provider/model for this call
        orig_provider = get_setting("chat_provider")
        orig_model = get_setting("chat_model")

        set_setting("chat_provider", provider)
        set_setting("chat_model", model)

        try:
            updated = _chat_fn(message, history)
            result_status = f"*Last: {provider}/{model} · {len(updated)} messages*"
            return updated, updated, "", result_status
        except Exception as e:
            error_history = history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": f"Error: {str(e)}"},
            ]
            return error_history, error_history, "", f"*Error: {str(e)[:80]}*"
        finally:
            # Restore original settings
            set_setting("chat_provider", orig_provider)
            set_setting("chat_model", orig_model)

    def _chat_tab_update_models(provider):
        """Update model dropdown when provider changes."""
        preset = PROVIDER_PRESETS.get(provider, {})
        return gr.Dropdown(
            choices=preset.get("models", []),
            value=preset.get("default_model", ""),
        )

    chat_tab_input.submit(
        _chat_tab_send,
        inputs=[chat_tab_input, chat_tab_history, chat_tab_provider, chat_tab_model],
        outputs=[chat_tab_chatbot, chat_tab_history, chat_tab_input, chat_tab_status],
        api_visibility="private",
    )

    chat_tab_send.click(
        _chat_tab_send,
        inputs=[chat_tab_input, chat_tab_history, chat_tab_provider, chat_tab_model],
        outputs=[chat_tab_chatbot, chat_tab_history, chat_tab_input, chat_tab_status],
        api_visibility="private",
    )

    chat_tab_clear.click(
        lambda: (list(INITIAL_CHAT), list(INITIAL_CHAT), "*Ready*"),
        outputs=[chat_tab_chatbot, chat_tab_history, chat_tab_status],
        api_visibility="private",
    )

    chat_tab_provider.change(
        _chat_tab_update_models,
        inputs=[chat_tab_provider],
        outputs=[chat_tab_model],
        api_visibility="private",
    )
```

---

## Task 4: Update CLAUDE.md

Update the status line:
```
**Status:** Phase 4 — Local LLM integration, Chat tab
```

Update the tab table to show five tabs:

```markdown
| Tab | Left Sidebar | Center | Status |
|-----|-------------|--------|--------|
| **Projects** | Project cards, filters, + New | Detail editor, List View | ✅ Working |
| **Work** | Task cards, filters, + New Task | Task detail, List View | ✅ Working |
| **Knowledge** | Document cards, filters, + New Doc | Documents (Detail/List), Search, Connections | ✅ Working |
| **Chat** | Info/help text | Full-width chat, provider/model selector | ✅ Working |
| **Admin** | Quick Settings (provider/model/key) | System Prompt editor, Stats, Backup/Restore | ✅ Working |
```

---

## Execution Order

1. **Mat:** Complete P1-P4 (pull image, rebuild stack, pull model, verify)
2. Agent: Task 1 (settings default — one line)
3. Agent: Task 2 (chat.py presets — one dict)
4. Agent: Task 3 (Chat tab — pages/projects.py)
5. Agent: Task 4 (CLAUDE.md)

## Smoke Tests

### Test A: Ollama via sidebar chat
1. Go to Admin tab
2. In left sidebar Quick Settings, select Provider: `ollama`
3. Model should auto-populate with `nemotron-3-nano:latest`
4. Base URL should show `http://ollama:11434/v1`
5. Send a message in the right sidebar chat: "List all projects"
6. Verify response comes from local model
7. If tool use works: bonus. If not: model should still respond with text

### Test B: Chat tab with local model
1. Click the Chat tab
2. Right panel should show Provider: `ollama`, Model: `nemotron-3-nano:latest`
3. Send: "Hello, what model are you?"
4. Verify response appears in the full-width chatbot
5. Switch provider to `anthropic` or `gemini` — verify model dropdown updates
6. Switch back to `ollama` — verify it works again
7. Click "Clear Chat" — verify chat resets

### Test C: Chat tab with cloud model
1. On Chat tab, switch provider to `anthropic`
2. Enter your API key in Admin sidebar (if not already set)
3. Send: "List all items in the database"
4. Verify Claude responds with tool use (should call list_items)
5. Switch back to ollama — verify local model still works

### Test D: Sidebar chat independence
1. While on Chat tab with ollama selected, open the sidebar chat
2. Sidebar should still use whatever provider is set in Admin settings
3. Verify both can work simultaneously without interfering

## Design Decisions

**Why a separate Chat tab instead of just the sidebar?**
- Sidebar is for quick DB operations while browsing other tabs
- Chat tab gives full-width space for longer conversations
- Chat tab has its OWN provider/model selector — independent of Admin settings
- This lets you test local models on Chat tab while keeping Claude in the sidebar
- Nemotron challenge demo surface: "here's the local model managing my project"

**Why temp-override settings in _chat_tab_send?**
- The chat() function reads provider/model from the settings DB
- The Chat tab needs its own provider/model independent of Admin
- We temporarily swap settings, call chat(), then restore originals
- Future improvement: refactor chat() to accept provider/model as parameters
  instead of reading from settings. But that's a larger refactor — not Phase 4.

**Why a second Ollama container instead of sharing?**
- janatopenwebui stack is a monolith that needs decomposing eventually
- JANATPMP needs to be self-contained (`docker compose up` and go)
- They share the external `ollama_data` volume so models are available to both
- Different host ports (11434 vs 11435) allow both to run simultaneously
- No dependency on janatopenwebui being up

## NOT in scope (Phase 5+)

- GPU passthrough tuning (context length, memory limits)
- Chat history persistence (save conversations to documents table)
- Streaming responses (Gradio supports this but adds complexity)
- Model pull/management UI within JANATPMP
- Refactor chat() to accept provider/model as parameters
- Tab state persistence across tab switches
- Decompose janatopenwebui stack
