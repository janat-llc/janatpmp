"""Intent Engine — Stateful hypothesis tracking across conversation turns.

Wraps the fast intent_router (R26) with accumulated confidence, retrospective
detection, Primal Encoding gates, and action intent recommendations.

R35: Intent Engine — Cognition as Conversation Participant

The engine reads its own prior hypotheses from system/intent messages,
accumulates confidence via EMA, and writes new signals back as messages.
Zero LLM calls — only dict ops + one DB read on first call.

The action layer maps high-confidence hypotheses to concrete MCP tool
recommendations. Actions are observe-only in R35 (executed=False always).
Dispatch comes in a future sprint.

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

# Status extraction from update signals
_STATUS_EXTRACT = re.compile(
    r"as\s+(done|complete|finished|in.?progress|started|blocked|not.?started)",
    re.IGNORECASE,
)

# Query filter extraction
_QUERY_STATUS_EXTRACT = re.compile(
    r"(pending|active|blocked|completed?|done|in.?progress|not.?started)",
    re.IGNORECASE,
)


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
    """A concrete MCP tool recommendation from the intent engine.

    Observe-only in R35 — executed is always False. The field exists
    for the future dispatch layer.
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
        # PLANNING hypothesis above threshold + creation language in message
        planning_h = hypotheses.get("planning")
        if (planning_h
                and planning_h.confidence >= create_thresh
                and _CREATE_SIGNALS.search(text)):
            actions.append(RecommendedAction(
                tool="create_item",
                params={"entity_type": "feature", "domain": "", "title": ""},
                confidence=round(planning_h.confidence, 3),
                reasoning=(
                    f"Planning hypothesis at {planning_h.confidence:.2f} "
                    f"with creation language detected"
                ),
            ))

        # Creative hypothesis above threshold + creation language
        creative_h = hypotheses.get("creative")
        if (creative_h
                and creative_h.confidence >= create_thresh
                and _CREATE_SIGNALS.search(text)):
            actions.append(RecommendedAction(
                tool="create_item",
                params={"entity_type": "initiative", "domain": "", "title": ""},
                confidence=round(creative_h.confidence, 3),
                reasoning=(
                    f"Creative hypothesis at {creative_h.confidence:.2f} "
                    f"with creation language detected"
                ),
            ))

        # --- Update actions ---
        if _UPDATE_SIGNALS.search(text):
            status_match = _STATUS_EXTRACT.search(text)
            status_val = ""
            if status_match:
                raw = status_match.group(1).lower().strip()
                # Normalize to DB enum values
                if raw in ("done", "complete", "finished"):
                    status_val = "completed"
                elif raw in ("started", "in progress", "in-progress"):
                    status_val = "in_progress"
                elif raw == "blocked":
                    status_val = "blocked"
                elif raw in ("not started", "not-started"):
                    status_val = "not_started"

            # Check if any hypothesis is confident enough
            max_conf = max(
                (h.confidence for h in hypotheses.values()), default=0.0
            )
            if max_conf >= update_thresh:
                actions.append(RecommendedAction(
                    tool="update_item",
                    params={"item_id": "", "status": status_val},
                    confidence=round(max_conf, 3),
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
