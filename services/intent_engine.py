"""Intent Engine — Stateful hypothesis tracking across conversation turns.

Wraps the fast intent_router (R26) with accumulated confidence, retrospective
detection, Primal Encoding gates, and action intent recommendations.

R35: Intent Engine — Cognition as Conversation Participant
R37: Intent Dispatch — Wire Action Execution into Chat Pipeline

The engine reads its own prior hypotheses from system/intent messages,
accumulates confidence via EMA, and writes new signals back as messages.
Zero LLM calls — only dict ops + one DB read on first call.

The action layer maps high-confidence hypotheses to concrete MCP tool
recommendations. R37 closes the loop: high-confidence actions are executed
via db_ops, with confidence-gated confirmation for medium-confidence actions.

Critical invariant: All failures fall back to classify_intent().
"""

import re
import json
import logging
from dataclasses import dataclass, field

from services.intent_router import (
    IntentResult,
    MessageIntent,
    RAGDepth,
    classify_intent,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Action Detection Patterns (pure regex, no LLM)
# ---------------------------------------------------------------------------

# Creation signals: "new project", "build a feature", "add an item for X"
_CREATE_SIGNALS = re.compile(
    r"(new\s+(project|feature|epic|initiative|idea)|"
    r"(create|add|start|build|make)\s+(a\s+)?(project|feature|epic|item|task)|"
    r"i('?m|\s+am)\s+(thinking\s+of|going\s+to|planning\s+to)\s+(build|create|start|make))",
    re.IGNORECASE,
)

# Update signals: "mark X as done", "update the status", "change priority"
_UPDATE_SIGNALS = re.compile(
    r"(mark\s+.{1,40}\s+as\s+(done|complete|finished|in.?progress|started|blocked)|"
    r"(update|change|set)\s+(the\s+)?(status|priority|title|description)\s+(of|for|on)|"
    r"(move|promote|demote)\s+.{1,40}\s+to\s+)",
    re.IGNORECASE,
)

# Query signals: "what tasks", "show me items", "list pending", "what's the status"
_QUERY_SIGNALS = re.compile(
    r"(what\s+(tasks?|items?|projects?)\s+(are|is|do)|"
    r"(show|list|find|get)\s+(me\s+)?(all\s+)?(tasks?|items?|projects?|pending|active)|"
    r"what('?s|\s+is)\s+the\s+status\s+of|"
    r"how\s+many\s+(tasks?|items?|projects?)|"
    r"(any|are\s+there)\s+(pending|open|active|blocked)\s+(tasks?|items?))",
    re.IGNORECASE,
)

# Status extraction from update signals (expanded R37)
_STATUS_EXTRACT = re.compile(
    r"(?:to|as|is)\s+(done|complete|finished|shipped|in.?progress|started|blocked|"
    r"not.?started|planning|review|archived|pending|processing|failed)",
    re.IGNORECASE,
)

# Query filter extraction
_QUERY_STATUS_EXTRACT = re.compile(
    r"(pending|active|blocked|completed?|done|in.?progress|not.?started)",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# R37: Subject Extraction & Dispatch Patterns
# ---------------------------------------------------------------------------

# Subject extraction — pull entity names from action language
_SUBJECT_EXTRACT = re.compile(
    r"(?:move|mark|update|change|set|promote|demote)\s+['\"]?(.{3,60}?)['\"]?\s+(?:to|as|from)\s+",
    re.IGNORECASE,
)

# Softer subject extraction: "{name} is done", "{name} is in progress"
_SOFT_SUBJECT_EXTRACT = re.compile(
    r"^(.{3,60}?)\s+(?:is|are)\s+(?:done|complete|finished|shipped|in.?progress|blocked)",
    re.IGNORECASE,
)

_CREATE_SUBJECT = re.compile(
    r"(?:create|add|make|new)\s+(?:a\s+)?(?:feature|epic|item|task|project|component)\s+"
    r"(?:for|called|named|about|:)\s+['\"]?(.{3,80})['\"]?",
    re.IGNORECASE,
)

# Softer update signals — conversational style (R37 Step 3)
_SOFT_UPDATE_SIGNALS = re.compile(
    r"((?:that|it|this)\s+(?:is|should\s+be)\s+(?:done|complete|finished|in.?progress|blocked|shipped)|"
    r"(?:we|i)\s+(?:finished|completed|shipped|started|blocked)\s+(?:that|it|this|the)\b|"
    r"(?:let'?s?|can\s+you)\s+move\s+.{1,40}\s+to\s+|"
    r"(?:put|set)\s+.{1,40}\s+(?:in|to|as)\s+|"
    r".{3,40}\s+(?:is|are)\s+(?:done|complete|finished|shipped|in.?progress|blocked)(?:\s|$))",
    re.IGNORECASE,
)

# Confirmation signals for pending actions
_CONFIRM_SIGNALS = re.compile(
    r"^(yes|yeah|yep|do it|go ahead|confirmed?|please|ok|sure|yup)\s*[.!]?$",
    re.IGNORECASE,
)

# R37: Dispatch thresholds and safety boundary
DISPATCH_AUTO_THRESHOLD = 0.75    # Above: execute silently
DISPATCH_CONFIRM_THRESHOLD = 0.5  # Between confirm and auto: ask first
DISPATCH_ALLOWED_TOOLS = {"update_item", "create_item", "update_task", "create_task"}


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class Hypothesis:
    """A tracked intent hypothesis across turns."""
    intent: str               # MessageIntent.value
    confidence: float         # Accumulated via EMA
    first_seen_turn: int
    last_seen_turn: int
    occurrences: int
    reasoning: str


@dataclass
class RecommendedAction:
    """A concrete tool recommendation from the intent engine.

    R37: dispatch_actions() sets executed=True after successful db_ops calls.
    """
    tool: str              # MCP tool name: "create_item", "update_task", etc.
    params: dict           # Tool parameters
    confidence: float      # Confidence this action is warranted
    reasoning: str         # Why the engine recommends this
    executed: bool = False # Always False in R35 — observe only


@dataclass
class EngineResult:
    """Full result from intent engine processing."""
    intent_result: IntentResult
    hypotheses: dict[str, Hypothesis] = field(default_factory=dict)
    recommended_actions: list[RecommendedAction] = field(default_factory=list)
    is_retrospective_turn: bool = False
    retrospective_notes: str = ""
    system_message_content: str = ""
    suppress_planning: bool = False
    patience_mode: bool = False


# ---------------------------------------------------------------------------
# Intent Engine
# ---------------------------------------------------------------------------

class IntentEngine:
    """Stateful intent engine for a single conversation.

    Tracks hypotheses across turns, detects retrospective patterns,
    and gates actions via Constitution/Attribute/Preference primitives.
    """

    def __init__(self, conversation_id: str, window_size: int = 10):
        self.conversation_id = conversation_id
        self.window_size = window_size
        self.hypotheses: dict[str, Hypothesis] = {}
        self._loaded = False
        self._history: list[dict] = []  # Recent system/intent message content
        self._pending_actions: list[RecommendedAction] = []  # R37: awaiting confirmation

    def _load_prior_hypotheses(self) -> None:
        """Rebuild hypothesis state from persisted system/intent messages."""
        if self._loaded:
            return
        self._loaded = True
        try:
            from db.chat_operations import get_messages_by_role
            msgs = get_messages_by_role(
                self.conversation_id,
                role="system/intent",
                limit=self.window_size,
            )
            for msg in msgs:
                content = msg.get("user_prompt", "")
                if not content:
                    continue
                try:
                    data = json.loads(content)
                    self._history.append(data)
                    # Rebuild hypotheses from the latest signal
                    for h in data.get("active_hypotheses", []):
                        intent_key = h.get("intent", "")
                        if intent_key:
                            self.hypotheses[intent_key] = Hypothesis(
                                intent=intent_key,
                                confidence=h.get("confidence", 0.0),
                                first_seen_turn=h.get("first_seen_turn", 0),
                                last_seen_turn=h.get("last_seen_turn", 0),
                                occurrences=h.get("occurrences", 1),
                                reasoning=h.get("reasoning", ""),
                            )
                except (json.JSONDecodeError, KeyError):
                    continue
        except Exception as e:
            logger.debug("Intent engine: failed to load prior hypotheses: %s", e)

    def process(
        self,
        message: str,
        conversation_turn_count: int,
        retrospective_interval: int = 5,
        ema_weight: float = 0.3,
    ) -> EngineResult:
        """Process a message through the intent engine.

        Args:
            message: The user's message text.
            conversation_turn_count: Current turn number.
            retrospective_interval: Turns between retrospective checks.
            ema_weight: Weight for new signal in EMA (0-1). Higher = faster adaptation.

        Returns:
            EngineResult with enriched classification and hypothesis state.
        """
        # 1. Lazy-load prior hypotheses
        self._load_prior_hypotheses()

        # 2. Fast classification (the reflex)
        intent_result = classify_intent(message, conversation_turn_count)
        current_intent = intent_result.intent.value
        current_confidence = intent_result.confidence

        # 3. Update hypothesis dict via EMA + conviction boost
        if current_intent in self.hypotheses:
            h = self.hypotheses[current_intent]
            h.confidence = (1 - ema_weight) * h.confidence + ema_weight * current_confidence
            h.last_seen_turn = conversation_turn_count
            h.occurrences += 1
            h.reasoning = intent_result.reasoning
            # Conviction boost: sustained hypotheses exceed raw classifier ceiling.
            # +0.05 per occurrence beyond 2, capped at +0.20. Makes 3+ occurrences
            # break through the classifier's confidence ceiling.
            if h.occurrences > 2:
                boost = min(0.05 * (h.occurrences - 2), 0.20)
                h.confidence = min(h.confidence + boost, 1.0)
        else:
            self.hypotheses[current_intent] = Hypothesis(
                intent=current_intent,
                confidence=current_confidence,
                first_seen_turn=conversation_turn_count,
                last_seen_turn=conversation_turn_count,
                occurrences=1,
                reasoning=intent_result.reasoning,
            )

        # Decay hypotheses not seen this turn (gentle fade)
        for key, h in self.hypotheses.items():
            if key != current_intent:
                h.confidence *= (1 - ema_weight * 0.5)  # Half-rate decay

        # Prune dead hypotheses (confidence < 0.05)
        self.hypotheses = {
            k: v for k, v in self.hypotheses.items() if v.confidence >= 0.05
        }

        # 4. Retrospective check
        is_retrospective = (
            conversation_turn_count > 0
            and conversation_turn_count % retrospective_interval == 0
        )
        retrospective_notes = ""
        if is_retrospective:
            retrospective_notes = self._run_retrospective(conversation_turn_count)

        # 5. Constitution gate: suppress planning if emotional hypothesis active
        suppress_planning = self._check_constitution_gate()

        # 6. Patience gate (Attribute): patience mode if recent continuations
        patience_mode = self._check_patience_gate(current_intent)

        # 7. Apply constitution gate to intent_result if needed
        if suppress_planning and intent_result.intent in (
            MessageIntent.PLANNING, MessageIntent.CREATIVE
        ):
            # Override to EMOTIONAL routing when emotional state is active
            intent_result = IntentResult(
                intent=intent_result.intent,
                confidence=intent_result.confidence,
                rag_depth=RAGDepth.NONE,
                run_precognition=True,
                reasoning=f"{intent_result.reasoning} [constitution gate: emotional state active]",
            )

        # 8. Evaluate recommended actions
        action_thresholds = self._load_action_thresholds()
        recommended_actions = self._evaluate_actions(
            message, self.hypotheses, conversation_turn_count,
            thresholds=action_thresholds,
        )

        # 9. Serialize full state as system message content
        system_content = self._serialize_signal(
            turn=conversation_turn_count,
            fast_classification={
                "intent": current_intent,
                "confidence": round(current_confidence, 3),
                "reasoning": intent_result.reasoning,
            },
            is_retrospective=is_retrospective,
            retrospective_notes=retrospective_notes,
            suppress_planning=suppress_planning,
            patience_mode=patience_mode,
            intent_result=intent_result,
            recommended_actions=recommended_actions,
        )

        return EngineResult(
            intent_result=intent_result,
            hypotheses=dict(self.hypotheses),
            recommended_actions=recommended_actions,
            is_retrospective_turn=is_retrospective,
            retrospective_notes=retrospective_notes,
            system_message_content=system_content,
            suppress_planning=suppress_planning,
            patience_mode=patience_mode,
        )

    def _run_retrospective(self, current_turn: int) -> str:
        """Analyze hypothesis trajectory for drift and sustained patterns."""
        notes = []

        # Check for sustained mode (same intent dominant for 3+ consecutive turns)
        for key, h in self.hypotheses.items():
            span = h.last_seen_turn - h.first_seen_turn
            if h.occurrences >= 3 and span >= 2:
                notes.append(
                    f"Sustained {key} mode: {h.occurrences} occurrences "
                    f"over turns {h.first_seen_turn}-{h.last_seen_turn}, "
                    f"confidence {h.confidence:.2f}"
                )

        # Check for emotional transitions (emotional hypothesis that grew)
        emotional_h = self.hypotheses.get("emotional")
        if emotional_h and emotional_h.occurrences >= 2 and emotional_h.confidence > 0.4:
            notes.append(
                f"Emotional pattern escalating: confidence {emotional_h.confidence:.2f}, "
                f"{emotional_h.occurrences} occurrences"
            )

        # Check for intent drift (hypothesis that started weak but grew strong)
        for key, h in self.hypotheses.items():
            if (h.occurrences >= 2
                    and h.confidence > 0.6
                    and h.first_seen_turn < current_turn - 2):
                if len(self._history) >= 2:
                    # Check if it was weaker in earlier signals
                    for old_signal in self._history[-3:]:
                        for old_h in old_signal.get("active_hypotheses", []):
                            if (old_h.get("intent") == key
                                    and old_h.get("confidence", 0) < 0.3):
                                notes.append(
                                    f"Intent drift: {key} was {old_h['confidence']:.2f} "
                                    f"at turn {old_h.get('first_seen_turn', '?')}, "
                                    f"now {h.confidence:.2f}"
                                )
                                break

        return "; ".join(notes) if notes else ""

    def _check_constitution_gate(self) -> bool:
        """Constitution: suppress planning when emotional state is active."""
        emotional_h = self.hypotheses.get("emotional")
        return (
            emotional_h is not None
            and emotional_h.confidence > 0.3
            and emotional_h.occurrences >= 2
        )

    def _check_patience_gate(self, current_intent: str) -> bool:
        """Attribute: patience mode when user is thinking by talking."""
        continuation_h = self.hypotheses.get("continuation")
        clarification_h = self.hypotheses.get("clarification")
        cont_recent = (
            continuation_h is not None
            and continuation_h.occurrences >= 2
        )
        clar_recent = (
            clarification_h is not None
            and clarification_h.occurrences >= 2
        )
        return cont_recent or clar_recent

    # -------------------------------------------------------------------
    # R37: Entity Resolution + Action Dispatch
    # -------------------------------------------------------------------

    def _resolve_entity(self, action: RecommendedAction, text: str) -> RecommendedAction:
        """Resolve entity references in action params using FTS search."""
        if action.tool == "update_item" and not action.params.get("item_id"):
            match = _SUBJECT_EXTRACT.search(text) or _SOFT_SUBJECT_EXTRACT.search(text)
            if match:
                subject = match.group(1).strip()
                from db.operations import search_items
                results = search_items(query=subject, limit=3)
                if results:
                    best = results[0]
                    title = best.get("title", "")
                    # Strong match: subject substring of title or vice versa
                    if subject.lower() in title.lower() or title.lower() in subject.lower():
                        action.params["item_id"] = best["id"]
                        action.params["_resolved_title"] = title
                        action.confidence = min(action.confidence + 0.1, 1.0)
                    else:
                        # Weak match — lower confidence to trigger confirmation
                        action.params["item_id"] = best["id"]
                        action.params["_resolved_title"] = title
                        action.confidence = max(action.confidence - 0.2, 0.0)

        elif action.tool == "update_task" and not action.params.get("task_id"):
            # No FTS for tasks — use list_tasks with title scan
            match = _SUBJECT_EXTRACT.search(text) or _SOFT_SUBJECT_EXTRACT.search(text)
            if match:
                subject = match.group(1).strip().lower()
                from db.operations import list_tasks
                tasks = list_tasks(limit=50)
                for t in tasks:
                    if subject in t.get("title", "").lower():
                        action.params["task_id"] = t["id"]
                        action.params["_resolved_title"] = t["title"]
                        action.confidence = min(action.confidence + 0.1, 1.0)
                        break

        elif action.tool in ("create_item", "create_task"):
            match = _CREATE_SUBJECT.search(text)
            if match:
                action.params["title"] = match.group(1).strip()

        return action

    def dispatch_actions(
        self,
        actions: list[RecommendedAction],
        text: str,
    ) -> tuple[list[RecommendedAction], list[str]]:
        """Execute or queue actions based on confidence gating.

        Returns:
            (processed_actions, feedback_lines)
            - processed_actions: actions with executed=True where applicable
            - feedback_lines: human-readable strings to inject into Janus context
        """
        from services.settings import get_setting

        enabled = get_setting("intent_action_dispatch_enabled")
        if not enabled or enabled.lower() in ("false", "0", "no"):
            return actions, []

        # Read thresholds from settings (fall back to module constants)
        try:
            auto_thresh = float(get_setting("intent_dispatch_auto_threshold") or DISPATCH_AUTO_THRESHOLD)
        except (TypeError, ValueError):
            auto_thresh = DISPATCH_AUTO_THRESHOLD
        try:
            confirm_thresh = float(get_setting("intent_dispatch_confirm_threshold") or DISPATCH_CONFIRM_THRESHOLD)
        except (TypeError, ValueError):
            confirm_thresh = DISPATCH_CONFIRM_THRESHOLD

        feedback: list[str] = []
        for action in actions:
            if action.tool not in DISPATCH_ALLOWED_TOOLS:
                continue
            if action.executed:
                continue

            # Resolve entity references
            action = self._resolve_entity(action, text)

            if action.confidence >= auto_thresh:
                # HIGH confidence — execute immediately
                result = self._execute(action)
                if result:
                    action.executed = True
                    feedback.append(result)
            elif action.confidence >= confirm_thresh:
                # MEDIUM confidence — ask for confirmation
                desc = self._describe_action(action)
                feedback.append(f"[INTENT] I think you want me to: {desc}. Should I?")
                self._pending_actions.append(action)
            # Below confirm threshold — ignore silently

        return actions, feedback

    def _check_pending_confirmations(self, text: str) -> list[str]:
        """Check if user confirmed pending actions from previous turn."""
        if not self._pending_actions:
            return []
        if not _CONFIRM_SIGNALS.search(text.strip()):
            # Not a confirmation — clear pending
            self._pending_actions = []
            return []

        # Confirmed — execute all pending
        feedback: list[str] = []
        for action in self._pending_actions:
            result = self._execute(action)
            if result:
                action.executed = True
                feedback.append(result)
        self._pending_actions = []
        return feedback

    def _execute(self, action: RecommendedAction) -> str | None:
        """Execute a single action against the database. Returns feedback string or None."""
        from db.operations import update_item, create_item, update_task, create_task

        try:
            tool = action.tool
            params = {k: v for k, v in action.params.items() if not k.startswith("_")}
            resolved_title = action.params.get("_resolved_title", "")

            if tool == "update_item" and params.get("item_id"):
                update_item(**params)
                status = params.get("status", "")
                return f"[ACTION] Moved '{resolved_title or params['item_id'][:8]}' to {status}"

            elif tool == "create_item" and params.get("title"):
                # Ensure required fields have sensible defaults
                if not params.get("entity_type"):
                    params["entity_type"] = "feature"
                if not params.get("domain"):
                    # Use first active domain as default
                    from db.operations import get_domains
                    domains = get_domains(active_only=True)
                    params["domain"] = domains[0]["name"] if domains else "JANATPMP"
                new_id = create_item(**params)
                return f"[ACTION] Created item: '{params['title']}' ({new_id[:8]})"

            elif tool == "update_task" and params.get("task_id"):
                update_task(**params)
                status = params.get("status", "")
                return f"[ACTION] Updated task '{resolved_title or params['task_id'][:8]}' → {status}"

            elif tool == "create_task" and params.get("title"):
                # Ensure required fields have sensible defaults
                if not params.get("task_type"):
                    params["task_type"] = "user_story"
                new_id = create_task(**params)
                return f"[ACTION] Created task: '{params['title']}' ({new_id[:8]})"

            else:
                logger.warning("Dispatch: missing required params for %s: %s", tool, params)
                return None

        except Exception as e:
            logger.error("Dispatch failed for %s: %s", action.tool, e)
            return None

    def _describe_action(self, action: RecommendedAction) -> str:
        """Human-readable description of a pending action."""
        tool = action.tool
        params = action.params
        title = params.get("_resolved_title", params.get("title", params.get("item_id", "")[:8]))

        if tool == "update_item":
            return f"move '{title}' to {params.get('status', '?')}"
        elif tool == "create_item":
            return f"create a new {params.get('entity_type', 'item')} called '{title}'"
        elif tool == "update_task":
            return f"update task '{title}' to {params.get('status', '?')}"
        elif tool == "create_task":
            return f"create a new task: '{params.get('title', '?')}'"
        return f"{tool}({params})"

    def _evaluate_actions(
        self,
        message: str,
        hypotheses: dict[str, Hypothesis],
        turn: int,
        thresholds: dict[str, float] | None = None,
    ) -> list[RecommendedAction]:
        """Map high-confidence hypotheses to concrete MCP tool recommendations.

        Pure logic — zero LLM calls, zero I/O. Reads hypothesis confidence
        + message content to decide IF an action maps.

        Args:
            message: The user's raw message text.
            hypotheses: Current hypothesis dict.
            turn: Current conversation turn number.
            thresholds: Action confidence thresholds by category.
                Keys: "create", "update", "query". Defaults: 0.8, 0.7, 0.5.

        Returns:
            List of RecommendedAction (may be empty — most turns produce none).
        """
        if thresholds is None:
            thresholds = {}
        create_thresh = thresholds.get("create", 0.8)
        update_thresh = thresholds.get("update", 0.7)
        query_thresh = thresholds.get("query", 0.5)

        actions: list[RecommendedAction] = []
        text = message.strip()

        # --- Creation actions ---
        # R37: Direct create commands get confidence floor from regex match
        if _CREATE_SIGNALS.search(text):
            planning_h = hypotheses.get("planning")
            creative_h = hypotheses.get("creative")
            best_h = planning_h or creative_h
            # Explicit create language — floor at threshold so first-turn commands work
            base_conf = best_h.confidence if best_h else 0.5
            action_conf = max(base_conf, create_thresh)

            entity_type = "feature"
            if action_conf >= create_thresh:
                actions.append(RecommendedAction(
                    tool="create_item",
                    params={"entity_type": entity_type, "domain": "", "title": ""},
                    confidence=round(action_conf, 3),
                    reasoning=(
                        f"Creation language detected (conf floor applied), "
                        f"hypothesis={base_conf:.2f}"
                    ),
                ))

        # --- Update actions (R37: also check soft signals) ---
        is_strong_update = bool(_UPDATE_SIGNALS.search(text))
        is_soft_update = bool(_SOFT_UPDATE_SIGNALS.search(text))
        if is_strong_update or is_soft_update:
            status_match = _STATUS_EXTRACT.search(text)
            status_val = ""
            if status_match:
                raw = status_match.group(1).lower().strip()
                # Normalize to DB enum values (expanded R37)
                norm_map = {
                    "done": "completed", "complete": "completed", "finished": "completed",
                    "shipped": "shipped",
                    "started": "in_progress", "in progress": "in_progress", "in-progress": "in_progress",
                    "blocked": "blocked",
                    "not started": "not_started", "not-started": "not_started",
                    "planning": "planning",
                    "review": "review",
                    "archived": "archived",
                    "pending": "pending", "processing": "processing", "failed": "failed",
                }
                status_val = norm_map.get(raw, raw.replace(" ", "_").replace("-", "_"))

            # R37: Strong explicit commands use regex match as confidence floor.
            # Soft conversational signals still rely on hypothesis EMA.
            max_conf = max(
                (h.confidence for h in hypotheses.values()), default=0.0
            )
            if is_strong_update and status_val:
                # Explicit "move X to Y" — high-confidence action regardless of hypothesis
                action_conf = max(max_conf, 0.8)
            elif is_strong_update:
                action_conf = max(max_conf, 0.6)
            elif is_soft_update and status_val:
                # "X is done" — moderate confidence, dispatch will confirm or auto
                # based on entity resolution strength
                action_conf = max(max_conf, update_thresh)
            else:
                action_conf = max_conf

            if action_conf >= update_thresh:
                actions.append(RecommendedAction(
                    tool="update_item",
                    params={"item_id": "", "status": status_val},
                    confidence=round(action_conf, 3),
                    reasoning=f"Update language detected with status '{status_val}'",
                ))

        # --- Query actions ---
        if _QUERY_SIGNALS.search(text):
            # Determine which tool to recommend
            query_status = ""
            status_match = _QUERY_STATUS_EXTRACT.search(text)
            if status_match:
                raw = status_match.group(1).lower().strip()
                if raw in ("pending", "not started", "not-started"):
                    query_status = "not_started"
                elif raw in ("active", "in progress", "in-progress", "started"):
                    query_status = "in_progress"
                elif raw in ("completed", "complete", "done"):
                    query_status = "completed"
                elif raw == "blocked":
                    query_status = "blocked"

            # Decide: list_tasks vs list_items based on message content
            is_task_query = bool(re.search(r"\btasks?\b", text, re.IGNORECASE))
            tool_name = "list_tasks" if is_task_query else "list_items"
            params = {"status": query_status} if query_status else {}

            knowledge_h = hypotheses.get("knowledge")
            conf = knowledge_h.confidence if knowledge_h else 0.5
            if conf >= query_thresh:
                actions.append(RecommendedAction(
                    tool=tool_name,
                    params=params,
                    confidence=round(conf, 3),
                    reasoning=f"Query language detected targeting {tool_name}",
                ))

        # --- Emotional: explicitly NO action (presence, not tooling) ---
        # Emotional patterns produce empty actions list. That's correct.

        return actions

    @staticmethod
    def _load_action_thresholds() -> dict[str, float]:
        """Load action confidence thresholds from settings."""
        defaults = {"create": 0.8, "update": 0.7, "query": 0.5}
        try:
            from services.settings import get_setting
            for key in ("create", "update", "query"):
                val = get_setting(f"intent_action_threshold_{key}")
                if val:
                    defaults[key] = float(val)
        except Exception:
            pass
        return defaults

    def _serialize_signal(
        self,
        turn: int,
        fast_classification: dict,
        is_retrospective: bool,
        retrospective_notes: str,
        suppress_planning: bool,
        patience_mode: bool,
        intent_result: IntentResult,
        recommended_actions: list[RecommendedAction] | None = None,
    ) -> str:
        """Serialize the full intent signal as JSON for system/intent message."""
        active_hypotheses = []
        for key, h in sorted(
            self.hypotheses.items(),
            key=lambda x: x[1].confidence,
            reverse=True,
        ):
            active_hypotheses.append({
                "intent": h.intent,
                "confidence": round(h.confidence, 3),
                "first_seen_turn": h.first_seen_turn,
                "last_seen_turn": h.last_seen_turn,
                "occurrences": h.occurrences,
                "reasoning": h.reasoning,
            })

        actions_list = []
        for a in (recommended_actions or []):
            actions_list.append({
                "tool": a.tool,
                "params": a.params,
                "confidence": a.confidence,
                "reasoning": a.reasoning,
                "executed": a.executed,
            })

        signal = {
            "turn": turn,
            "fast_classification": fast_classification,
            "active_hypotheses": active_hypotheses,
            "recommended_actions": actions_list,
            "routing": {
                "rag_depth": intent_result.rag_depth.value,
                "run_precognition": intent_result.run_precognition,
            },
            "gates": {
                "suppress_planning": suppress_planning,
                "patience_mode": patience_mode,
            },
            "retrospective": retrospective_notes if is_retrospective else None,
        }
        return json.dumps(signal, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Module-level cache
# ---------------------------------------------------------------------------

_engines: dict[str, IntentEngine] = {}


def get_engine(conversation_id: str, window_size: int = 10) -> IntentEngine:
    """Get or create an IntentEngine for a conversation."""
    if conversation_id not in _engines:
        _engines[conversation_id] = IntentEngine(conversation_id, window_size)
    return _engines[conversation_id]


def clear_engine(conversation_id: str) -> None:
    """Clear cached engine for a conversation (e.g. on chapter archive)."""
    _engines.pop(conversation_id, None)
