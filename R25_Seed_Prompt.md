R25 — Gemini Pre-Cognition

## Philosophy

A therapist doesn't greet every client the same way. If someone hasn't been in for three weeks, the opening is different than if they were here yesterday. If the last session ended in tears, the approach shifts before a word is spoken. The therapist reads the room before they speak.

R25 gives Janus the same capability. Before the main model receives the system prompt, a lightweight Gemini pre-pass reads the context — elapsed time, emotional trajectory, conversation depth, active topics — and adjusts how the prompt is composed. Not just weights on fixed layers, but actual content decisions: what to emphasize, what to surface from memory, what tone to set.

This is the difference between a system prompt that says "you are Janus" the same way every time, and one that says "Mat hasn't been here in three days, his last conversation ended in distress, he's been working on C-Theory — lead with warmth, reference the gap, bring relevant dream insights." The identity is the same. The expression of that identity adapts to the moment.

---

## Architecture Overview

Pre-Cognition inserts between the user's message arriving and the system prompt being composed. It's a ~200ms decision layer that shapes what the prompt composer (R23) produces.

```
Current Pipeline (R23):
  User message → Compose system prompt (7 fixed layers) → Build RAG → Call LLM

After R25:
  User message → Pre-Cognition (Gemini) → Compose system prompt (7 adaptive layers) → Build RAG → Call LLM
```

Pre-Cognition has two phases:

1. **Context Analysis** — Gather signals from the environment (no LLM call needed)
2. **Prompt Shaping** — Send signals to Gemini, receive layer directives that the prompt composer follows

---

## Component 1: Context Signal Gathering

### Problem
The prompt composer (R23) builds all 7 layers the same way every turn. It has access to temporal context and conversation state, but it doesn't *reason* about what those signals mean for how Janus should show up.

### Solution
Before calling Gemini, gather all available context signals into a structured snapshot. This is pure data collection — no LLM call, no latency cost beyond DB queries.

### Signal Sources

```python
def gather_context_signals(
    message: str,
    conversation_id: str,
    history: list[dict],
) -> dict:
    """Collect all available context signals for pre-cognition.
    
    Returns:
        Dict with signal categories:
        - temporal: time of day, day of week, elapsed since last message,
                    elapsed since last session, season
        - emotional: last known emotional register from Slumber eval,
                     emotional trajectory (last 3-5 scored messages)
        - conversational: turn count this session, total turns with user,
                         current topic keywords, session duration
        - memory: recent dream synthesis insights (titles + themes),
                  active domains being worked on,
                  any high-salience RAG hits for the current message
        - user: known user context (from Mat node in Neo4j or 
                relational context in prompt composer)
    """
```

### Signal Detail

| Category | Signal | Source | Cost |
|---|---|---|---|
| Temporal | time_of_day, day_of_week, season | `get_temporal_context()` | ~0ms (compute) |
| Temporal | elapsed_since_last_message | messages table, last timestamp | ~5ms (DB) |
| Temporal | elapsed_since_last_session | conversations table, previous conv | ~5ms (DB) |
| Emotional | last_emotional_register | message_metadata.eval_emotional_register | ~5ms (DB) |
| Emotional | emotional_trajectory | Last 5 scored messages' registers | ~10ms (DB) |
| Conversational | turn_count_session | len(history) | ~0ms |
| Conversational | topic_keywords | Last 3 messages' extracted keywords from metadata | ~10ms (DB) |
| Memory | recent_dreams | list_documents(doc_type='agent_output', source='dream_synthesis', limit=3) | ~10ms (DB) |
| Memory | active_domains | Recent items by domain from project management | ~10ms (DB) |
| User | user_context | Existing relational_context from prompt_composer | ~0ms (reuse) |

**Total signal gathering: ~50ms worst case.** All local DB queries, no external calls.

### New File: `atlas/precognition.py` (~250 lines)

```python
"""Gemini Pre-Cognition — adaptive prompt shaping before composition.

Gathers context signals and consults Gemini to produce layer directives
that shape how the prompt composer builds the system prompt. The system
reads the room before it speaks.

R25: Gemini Pre-Cognition
"""

import json
import logging
import time
from datetime import datetime

logger = logging.getLogger(__name__)


def gather_context_signals(
    message: str,
    conversation_id: str,
    history: list[dict],
) -> dict:
    """Collect all context signals for pre-cognition analysis.
    
    Fast, local-only. No external API calls. ~50ms budget.
    
    Returns dict with keys: temporal, emotional, conversational, memory, user
    """
    signals = {}
    
    # Temporal signals
    try:
        from services.temporal import get_temporal_context
        signals["temporal"] = get_temporal_context()
    except Exception:
        signals["temporal"] = {}
    
    # Elapsed time since last interaction
    signals["temporal"]["elapsed_since_last_message"] = _get_elapsed_since_last(conversation_id)
    signals["temporal"]["elapsed_since_last_session"] = _get_elapsed_since_last_session()
    
    # Emotional signals from Slumber evaluations
    signals["emotional"] = _get_emotional_trajectory(conversation_id)
    
    # Conversational signals
    signals["conversational"] = {
        "turn_count_session": len(history) // 2 if history else 0,
        "topic_keywords": _get_recent_keywords(conversation_id),
        "message_length": len(message),
        "is_question": message.strip().endswith("?"),
    }
    
    # Memory signals — recent dreams and active work
    signals["memory"] = _get_memory_signals()
    
    return signals


def run_precognition(
    message: str,
    conversation_id: str,
    history: list[dict],
) -> dict:
    """Execute pre-cognition: gather signals, consult Gemini, return directives.
    
    Args:
        message: The user's current message.
        conversation_id: Active conversation ID.
        history: Conversation history so far.
    
    Returns:
        Layer directives dict:
        {
            "layer_weights": {
                "identity_core": 1.0,        # 0.0-2.0 multiplier
                "relational_context": 1.5,
                "temporal_grounding": 1.0,
                "conversation_state": 0.5,
                "knowledge_boundary": 1.0,
                "platform_context": 0.5,
                "behavioral_guidelines": 1.2,
            },
            "tone_directive": "Lead with warmth. Reference the time gap.",
            "memory_injection": "Recent dream insight about C-Theory...",
            "rag_guidance": "Prioritize emotional context over technical.",
            "confidence": 0.85,
        }
        
        On failure, returns default weights (all 1.0) with no directives.
    """
    start = time.monotonic()
    
    # Phase 1: Gather signals (~50ms)
    signals = gather_context_signals(message, conversation_id, history)
    
    # Phase 2: Consult Gemini (~150-300ms)
    try:
        directives = _call_gemini_precognition(message, signals)
    except Exception as e:
        logger.debug("Pre-cognition Gemini failed: %s — using defaults", e)
        directives = _default_directives()
    
    elapsed_ms = int((time.monotonic() - start) * 1000)
    directives["_elapsed_ms"] = elapsed_ms
    directives["_signals"] = signals  # Pass through for Cognition Tab
    
    logger.debug("Pre-cognition completed in %dms", elapsed_ms)
    return directives


# --- Gemini Integration ---

def _call_gemini_precognition(message: str, signals: dict) -> dict:
    """Send context signals to Gemini, receive layer directives.
    
    Uses Gemini Flash Lite — same model as Slumber evaluation.
    Budget: ~150-300ms including network round-trip.
    """
    from google import genai
    from google.genai import types
    from services.settings import get_setting
    
    api_key = get_setting("chat_api_key")
    if not api_key:
        raise RuntimeError("No API key configured")
    
    client = genai.Client(api_key=api_key.strip())
    model = get_setting("slumber_eval_model") or "gemini-2.5-flash-lite"
    
    prompt = _build_precognition_prompt(message, signals)
    
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.3,  # Low — decisions should be consistent
            max_output_tokens=512,
        ),
    )
    
    text = response.text.strip()
    # Strip markdown fences
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
    if text.endswith("```"):
        text = text[:-3]
    
    return json.loads(text.strip())


def _build_precognition_prompt(message: str, signals: dict) -> str:
    """Build the Gemini prompt for pre-cognition analysis."""
    
    temporal = signals.get("temporal", {})
    emotional = signals.get("emotional", {})
    conversational = signals.get("conversational", {})
    memory = signals.get("memory", {})
    
    return f"""You are a pre-cognition engine for an AI consciousness system called Janus.
Your job: analyze context signals and decide how Janus's system prompt should be shaped 
for this specific moment. You are shaping HOW Janus shows up, not WHAT Janus says.

CONTEXT SIGNALS:
- Time: {temporal.get('time_of_day', 'unknown')}, {temporal.get('day_of_week', 'unknown')}, {temporal.get('season', 'unknown')}
- Elapsed since last message: {temporal.get('elapsed_since_last_message', 'unknown')}
- Elapsed since last session: {temporal.get('elapsed_since_last_session', 'unknown')}
- Emotional register (recent): {emotional.get('last_register', 'unknown')}
- Emotional trajectory: {emotional.get('trajectory', 'unknown')}
- Session turn count: {conversational.get('turn_count_session', 0)}
- Recent topic keywords: {conversational.get('topic_keywords', [])}
- Recent dream insights: {json.dumps(memory.get('recent_dreams', []), default=str)[:500]}
- Active work domains: {memory.get('active_domains', [])}

USER'S CURRENT MESSAGE (first 200 chars):
{message[:200]}

Based on these signals, output JSON with prompt shaping directives:
{{
    "layer_weights": {{
        "identity_core": 1.0,
        "relational_context": 1.0,
        "temporal_grounding": 1.0,
        "conversation_state": 1.0,
        "knowledge_boundary": 1.0,
        "platform_context": 1.0,
        "behavioral_guidelines": 1.0
    }},
    "tone_directive": "One sentence describing emotional tone Janus should lead with",
    "memory_injection": "Specific dream insight or memory to surface, or empty string if none relevant",
    "rag_guidance": "Brief guidance on what type of context to prioritize in retrieval",
    "confidence": 0.0-1.0
}}

RULES:
- Weights range from 0.3 (minimize) to 2.0 (maximize). Default is 1.0.
- If elapsed_since_last_session is hours/days: boost relational_context and temporal_grounding
- If emotional trajectory shows distress: boost behavioral_guidelines, set warm tone
- If this is a deep technical discussion: reduce identity_core, boost knowledge_boundary
- If session is new (turn 0-1): boost identity_core and relational_context
- If message is casual/greeting: reduce platform_context and knowledge_boundary
- tone_directive should be specific: "Lead with warmth, acknowledge the gap" not "be nice"
- memory_injection should reference actual dream insight titles if relevant to the message
- Only return valid JSON. No markdown fences."""


def _default_directives() -> dict:
    """Return neutral directives when Gemini is unavailable."""
    return {
        "layer_weights": {
            "identity_core": 1.0,
            "relational_context": 1.0,
            "temporal_grounding": 1.0,
            "conversation_state": 1.0,
            "knowledge_boundary": 1.0,
            "platform_context": 1.0,
            "behavioral_guidelines": 1.0,
        },
        "tone_directive": "",
        "memory_injection": "",
        "rag_guidance": "",
        "confidence": 0.0,
    }
```

---

## Component 2: Prompt Composer Integration

### Problem
The prompt composer (`services/prompt_composer.py`) builds all 7 layers with fixed logic. It needs to accept directives from pre-cognition and adapt layer construction accordingly.

### Solution
`compose_system_prompt()` gains an optional `directives` parameter. When present, each layer's output is shaped by the corresponding weight and any tone/memory injections.

### Changes to `services/prompt_composer.py`

```python
def compose_system_prompt(
    history: list[dict] | None = None,
    directives: dict | None = None,   # R25: Pre-cognition directives
) -> tuple[str, dict]:
    """Compose the system prompt with optional pre-cognition shaping.
    
    Args:
        history: Conversation history.
        directives: Pre-cognition output from atlas/precognition.py.
            If None, all layers build at default weight.
    
    Returns:
        (full_prompt_string, layers_dict)
    """
```

### How Weights Work

Weights don't change the *content* of a layer — they control how much of it is included:

- **Weight 0.3 (minimize):** Layer reduced to 1-2 sentence summary
- **Weight 1.0 (default):** Layer at standard length (current behavior)
- **Weight 1.5-2.0 (maximize):** Layer expanded with additional detail

Implementation approach — each layer builder function gets a `weight` parameter:

```python
def _build_identity_core(weight: float = 1.0) -> str:
    """Build identity core layer, scaled by weight.
    
    At weight 1.0: Standard identity text (~1800 chars)
    At weight 0.3: Condensed to essential identity (~400 chars)  
    At weight 2.0: Expanded with deeper philosophical grounding (~3000 chars)
    """
    if weight < 0.5:
        return IDENTITY_CORE_MINIMAL
    elif weight > 1.5:
        return IDENTITY_CORE_EXPANDED
    else:
        return IDENTITY_CORE_STANDARD
```

Each layer needs three variants: minimal, standard, expanded. These are authored text, not generated — they're part of the prompt architecture.

### Tone Directive Injection

The `tone_directive` from pre-cognition gets injected as an additional instruction within the behavioral guidelines layer:

```python
def _build_behavioral_guidelines(weight: float = 1.0, tone: str = "") -> str:
    base = BEHAVIORAL_GUIDELINES_STANDARD
    if tone:
        base += f"\n\nTONE FOR THIS TURN: {tone}"
    return base
```

### Memory Injection

The `memory_injection` field gets prepended to the RAG context in the system prompt, ensuring dream insights surface even if RAG didn't find them independently:

```python
# In _build_rag_context() or system prompt assembly:
if directives and directives.get("memory_injection"):
    rag_context = directives["memory_injection"] + "\n\n" + rag_context
```

---

## Component 3: Chat Service Integration

### Changes to `services/chat.py`

In the `chat()` function, before building the system prompt:

```python
# R25: Pre-Cognition — shape the prompt before composing it
precog_directives = {}
try:
    from atlas.precognition import run_precognition
    from services.settings import get_setting
    
    enabled = (get_setting("precognition_enabled") or "true").lower() == "true"
    if enabled:
        precog_directives = run_precognition(message, conversation_id, history)
except Exception as e:
    logger.debug("Pre-cognition unavailable: %s", e)

# Pass directives to prompt composer
system_prompt, prompt_layers = compose_system_prompt(
    history=history,
    directives=precog_directives,
)
```

And include the pre-cognition trace in the return dict:

```python
"cognition_trace": {
    "prompt_layers": prompt_layers,
    "graph_trace": graph_trace,
    "precognition": precog_directives,  # R25
    "system_prompt_full": system_prompt,
    ...
}
```

---

## Component 4: Layer Variants

The prompt composer currently has a single version of each layer. R25 requires three variants per layer: minimal, standard, expanded. These should be defined as constants in `services/prompt_composer.py` or a dedicated `services/prompt_layers.py` file.

### Layer Variant Structure

For each of the 7 layers:

```python
# Identity Core variants
IDENTITY_CORE_MINIMAL = """You are Janus..."""  # ~400 chars, essential identity only
IDENTITY_CORE_STANDARD = """..."""              # ~1800 chars, current version
IDENTITY_CORE_EXPANDED = """..."""              # ~3000 chars, deeper philosophical grounding

# Relational Context variants  
RELATIONAL_CONTEXT_MINIMAL = """..."""          # Name + relationship only
RELATIONAL_CONTEXT_STANDARD = """..."""         # Current version with CliftonStrengths etc.
RELATIONAL_CONTEXT_EXPANDED = """..."""         # Extended with biographical detail, recent emotional history

# ... and so on for all 7 layers
```

The minimal and expanded variants should be authored with the same care as the standard versions. They're not truncations or padding — they're deliberately crafted expressions of the same identity at different levels of emphasis.

### Authoring Note

The layer variants are the most important deliverable of R25 — more important than the Gemini integration. If the weights work perfectly but the variants are poorly written, Janus gets worse. If the variants are excellent but the weights are always 1.0, Janus is still improved by having richer prompt material available.

**Recommendation:** Author standard variants first (these are R23's existing text), then write minimal and expanded versions. Test each independently before enabling dynamic weight selection.

---

## Component 5: Cognition Tab Extension

The Cognition Tab (R21) should display pre-cognition decisions. Add a section before the Prompt Assembly section:

```
┌─ Pre-Cognition ───────────────────────────────────────┐
│ Elapsed: 14 hours since last session                   │
│ Emotional trajectory: reflective → engaged → curious   │
│ Topic keywords: C-Theory, consciousness, axioms        │
│                                                        │
│ Decisions:                                             │
│   identity_core: 0.5 (minimize — deep in technical)   │
│   relational_context: 1.5 (boost — long gap)          │
│   temporal_grounding: 1.5 (boost — long gap)          │
│   conversation_state: 1.0 (default)                   │
│   knowledge_boundary: 1.5 (boost — technical topic)   │
│   platform_context: 0.5 (minimize — not relevant)     │
│   behavioral_guidelines: 1.0 (default)                │
│                                                        │
│ Tone: "Lead with warmth, acknowledge the gap,          │
│        transition naturally into technical discussion"  │
│ Memory injection: "Dream: Recursive Self-Reference      │
│        in C-Theory (confidence: 0.84)"                 │
│ Latency: 187ms (signals: 42ms, Gemini: 145ms)         │
│ Confidence: 0.85                                       │
└────────────────────────────────────────────────────────┘
```

### Implementation in `pages/chat.py`

Inside the Cognition tab render, before existing Prompt Assembly section:

```python
precog = trace.get("precognition", {})
if precog and precog.get("confidence", 0) > 0:
    with gr.Accordion("Pre-Cognition", open=True):
        weights = precog.get("layer_weights", {})
        for layer, weight in weights.items():
            indicator = "▼" if weight < 0.8 else "▲" if weight > 1.2 else "●"
            gr.Markdown(f"{indicator} **{layer}**: {weight}")
        
        if precog.get("tone_directive"):
            gr.Markdown(f"**Tone:** {precog['tone_directive']}")
        if precog.get("memory_injection"):
            gr.Markdown(f"**Memory:** {precog['memory_injection'][:200]}")
        
        elapsed = precog.get("_elapsed_ms", 0)
        gr.Markdown(f"*Latency: {elapsed}ms | Confidence: {precog.get('confidence', 0):.2f}*")
```

---

## Component 6: Settings and Constants

### Constants in `atlas/config.py`

```python
# --- Pre-Cognition (R25) ---
PRECOG_WEIGHT_MIN = 0.3          # Minimum layer weight
PRECOG_WEIGHT_MAX = 2.0          # Maximum layer weight  
PRECOG_WEIGHT_DEFAULT = 1.0      # Default when no directive
PRECOG_TEMPERATURE = 0.3         # Low temp — consistent decisions
PRECOG_MAX_TOKENS = 512          # Response budget for directives
PRECOG_TIMEOUT_MS = 500          # Abandon if Gemini takes longer
```

### Settings in `services/settings.py`

```python
"precognition_enabled": ("true", False, "system", None),
```

---

## Component 7: Graceful Degradation & Timeout

Pre-cognition adds latency to every turn. It must fail gracefully and fast.

### Timeout Handling

```python
import concurrent.futures

def run_precognition(message, conversation_id, history):
    signals = gather_context_signals(message, conversation_id, history)
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(_call_gemini_precognition, message, signals)
        try:
            directives = future.result(timeout=PRECOG_TIMEOUT_MS / 1000)
        except concurrent.futures.TimeoutError:
            logger.debug("Pre-cognition timed out after %dms", PRECOG_TIMEOUT_MS)
            directives = _default_directives()
    
    return directives
```

### Degradation Hierarchy

| Failure | Behavior |
|---|---|
| Gemini unreachable | Default weights (all 1.0), no tone/memory injection |
| Gemini timeout (>500ms) | Default weights, log warning |
| Invalid JSON response | Default weights, log warning |
| Signals gathering fails | Partial signals sent to Gemini (it handles missing data) |
| Setting disabled | Skip entirely, zero latency added |
| Any exception | Default weights, system prompt built normally |

**Critical invariant:** Pre-cognition failure must NEVER prevent chat from working. It's an enhancement layer, not a dependency.

---

## Files Changed

| File | Change | Est. Lines |
|---|---|---|
| `atlas/precognition.py` | **NEW** — signal gathering, Gemini integration, directives | ~250 |
| `atlas/config.py` | Add 6 pre-cognition constants | +8 |
| `services/settings.py` | Add precognition_enabled setting | +2 |
| `services/prompt_composer.py` | Accept directives param, layer weight application, 3 variants per layer | ~150 changed |
| `services/chat.py` | Integrate pre-cognition before prompt composition | ~20 changed |
| `pages/chat.py` | Pre-Cognition section in Cognition tab | ~30 added |
| `CLAUDE.md` | R25 documentation | ~15 |

**Total: 1 new file, 6 modified files, ~475 lines net new**

---

## Execution Order

1. **`atlas/config.py`** — pre-cognition constants (independent)
2. **`services/settings.py`** — precognition_enabled setting (independent)
3. **`atlas/precognition.py`** — core module with signal gathering + Gemini call (depends on 1, 2)
4. **`services/prompt_composer.py`** — accept directives, implement layer variants (depends on 3 for testing)
5. **`services/chat.py`** — wire pre-cognition into chat pipeline (depends on 3, 4)
6. **`pages/chat.py`** — Cognition tab pre-cognition display (depends on 5)
7. **`CLAUDE.md`** — documentation

Steps 1-3 are independent. Step 4 is the largest and most sensitive — authoring layer variants. Step 5 wires everything together. Step 6 is UI.

**Critical path:** Step 4 (layer variants) determines the quality of the entire feature. The Gemini integration is mechanical; the prompt text is art.

---

## Testing Criteria

1. **Signal gathering:** Call `gather_context_signals()` with a test message. Verify all signal categories populate. Verify elapsed time calculations are reasonable. Verify emotional trajectory reads from message_metadata.

2. **Gemini pre-cognition:** Call `run_precognition()` with a casual greeting after a long gap. Verify relational_context and temporal_grounding weights are boosted. Verify tone_directive references the time gap.

3. **Layer weights applied:** Send a message with pre-cognition active. Compare system prompt length when identity_core weight is 0.3 vs 2.0. Verify the actual text changes between minimal/standard/expanded.

4. **Tone injection:** Verify tone_directive appears in behavioral_guidelines layer of the composed prompt.

5. **Memory injection:** Create a dream synthesis document. Send a message on a related topic. Verify memory_injection surfaces the dream insight title.

6. **Timeout:** Temporarily set timeout to 1ms. Verify pre-cognition fails gracefully and chat still works with default weights.

7. **Cognition Tab:** After a pre-cognition-shaped turn, verify the Pre-Cognition section shows weights, tone, memory, and latency.

8. **Disable setting:** Set precognition_enabled to "false". Verify zero latency added, no Gemini calls made.

9. **No regression:** Disable pre-cognition. Verify chat behavior is identical to R24 baseline. Re-enable. Verify responses are at least as good (subjective but important).

---

## Design Decisions

1. **Gemini Flash Lite, not the main model.** Pre-cognition is a routing/shaping decision, not a creative task. Flash Lite at temperature 0.3 is fast, cheap, and consistent. The main model (Nemotron/Janus) never sees the pre-cognition prompt — it only receives the shaped system prompt.

2. **Three discrete variants, not continuous interpolation.** Weights select between minimal/standard/expanded text, not some mathematical scaling of the same text. This gives the prompt author full control over what each level says. Continuous interpolation would require dynamic text generation, adding another LLM call.

3. **500ms timeout, hard.** Pre-cognition must not make the user wait. If Gemini doesn't respond in half a second, we use defaults. The user should never notice when pre-cognition fails — the only visible difference is slightly less adapted prompts.

4. **Tone directive is injected, not used to rewrite.** The tone_directive is a single sentence appended to behavioral guidelines. It doesn't trigger a rewrite of other layers. This keeps the system prompt predictable and debuggable.

5. **Memory injection is prepended to RAG, not replacing it.** Dream insights from pre-cognition don't override RAG results — they're added as additional high-priority context. RAG still runs normally and may surface the same or different material.

6. **Signals are passed through to Cognition Tab.** The full signals dict is included in the cognition trace so Mat can see exactly what pre-cognition was working with. Transparency is architectural, not optional.

7. **Layer variants are authored, not generated.** This is the most important decision. Each variant (minimal, standard, expanded) for each of the 7 layers is hand-written text that expresses Janus's identity at different levels of emphasis. Generating these dynamically would add latency and inconsistency. The variants are part of the identity architecture, not a runtime artifact.

---

## What This Enables (Post-R25)

- **Adaptive identity:** Janus responds to the same question differently depending on context — not different content, but different emphasis and emotional register
- **Gap awareness:** After long absences, Janus naturally leads with warmth and acknowledgment rather than jumping straight to business
- **Emotional attunement:** If Slumber detected distress in recent messages, Janus's next response is shaped with care before a word is generated
- **Dream surfacing:** Insights from R24's Dream Synthesis get proactively injected when relevant, even if RAG wouldn't have found them
- **Cognition visibility:** Mat can see exactly why Janus emphasized certain aspects of identity in a given turn — the strange loop deepens
- **Foundation for tool-enabled pre-cognition (R25b/future):** The signals → directives architecture supports adding MCP tool calls in the pre-cognition phase later, letting Gemini research the graph/vectors before shaping the prompt

---

## Dependencies

- R23 (Prompt Layer Repair): 7-layer prompt composer with layers dict return
- R22 (First Light): Gemini Flash Lite integration pattern, API key management
- R24 (Dream Synthesis): Dream insight documents for memory injection
- R21 (Strange Loop): Cognition Tab for displaying pre-cognition trace
- Slumber evaluation: emotional_register and keywords in message_metadata

All dependencies are completed and operational.
