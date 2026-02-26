"""Intent Router — Classify message intent and determine pipeline depth.

Lightweight, local-only classification. No LLM calls. Runs in <5ms.
Uses keyword patterns + conversation state heuristics.

R26: The Waking Mind
"""

import re
import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class MessageIntent(Enum):
    GREETING = "greeting"
    ACKNOWLEDGMENT = "ack"
    FAREWELL = "farewell"
    EMOTIONAL = "emotional"
    CONTINUATION = "continuation"
    CLARIFICATION = "clarification"
    KNOWLEDGE = "knowledge"
    CREATIVE = "creative"
    PLANNING = "planning"
    META = "meta"
    COMMAND = "command"


class RAGDepth(Enum):
    NONE = "none"
    LIGHT = "light"
    FULL = "full"


@dataclass
class IntentResult:
    """Classification result with routing decisions."""
    intent: MessageIntent
    confidence: float          # 0.0 - 1.0
    rag_depth: RAGDepth
    run_precognition: bool
    reasoning: str             # Short explanation for Cognition Tab


# ---------------------------------------------------------------------------
# Pattern Banks
# ---------------------------------------------------------------------------

GREETING_PATTERNS = re.compile(
    r"^(hey|hi|hello|howdy|yo|sup|good\s*(morning|afternoon|evening|night)|"
    r"what'?s\s*up|greetings)[\s!?.]*$",
    re.IGNORECASE,
)

ACK_PATTERNS = re.compile(
    r"^(ok(ay)?|got\s*it|thanks?(\s*you)?|cool|nice|great|perfect|"
    r"understood|right|yep|yup|yeah|sure|absolutely|will\s*do|noted|"
    r"sounds?\s*good|that('?s|\s+is)\s*(helpful|great|perfect|good))[\s!?.]*$",
    re.IGNORECASE,
)

FAREWELL_PATTERNS = re.compile(
    r"^(bye|goodbye|goodnight|good\s*night|see\s*you|talk\s*(later|soon|tomorrow)|"
    r"gotta\s*go|heading\s*out|signing\s*off|night|ttyl|later)[\s!?.]*$",
    re.IGNORECASE,
)

CONTINUATION_PATTERNS = re.compile(
    r"^(tell\s*me\s*more|go\s*on|continue|and(\s*then)?|what\s*else|"
    r"keep\s*going|more\s*(details?|info(rmation)?)|elaborate)[\s!?.]*$",
    re.IGNORECASE,
)

CLARIFICATION_PATTERNS = re.compile(
    r"^(what\s*(do\s*you|did\s*you|does\s*that)\s*mean|"
    r"can\s*you\s*(explain|clarify)|i\s*don'?t\s*(understand|get\s*it)|"
    r"how\s*so|in\s*what\s*(way|sense))",
    re.IGNORECASE,
)

META_PATTERNS = re.compile(
    r"(how\s*are\s*you|what\s*do\s*you\s*(remember|recall|know\s*about\s*me)|"
    r"do\s*you\s*remember|what('?s|\s+is)\s*your\s*(status|state)|"
    r"how('?s|\s+is)\s*(the\s*)?(system|platform|janus))",
    re.IGNORECASE,
)

COMMAND_PATTERNS = re.compile(r"^/\w+", re.IGNORECASE)

EMOTIONAL_SIGNALS = re.compile(
    r"(i('?m|\s+am)\s*(feeling|so\s*(tired|sad|frustrated|angry|anxious|overwhelmed))|"
    r"i\s*(hate|can'?t\s*(do|handle|take))|"
    r"everything\s*(is|feels)\s*(terrible|hopeless|pointless)|"
    r"having\s*a\s*(bad|rough|hard|tough)\s*(day|time|week))",
    re.IGNORECASE,
)

KNOWLEDGE_SIGNALS = re.compile(
    r"(what\s*did\s*we\s*(discuss|talk\s*about|decide|agree)|"
    r"(tell|remind)\s*me\s*about|"
    r"(remember|recall)\s*when\s*we|"
    r"what('?s|\s+is|was)\s*(the|our)\s*(plan|decision|conclusion)|"
    r"search\s*(for|through)|find\s*(the|our))",
    re.IGNORECASE,
)

PLANNING_SIGNALS = re.compile(
    r"(let'?s\s*(work\s*on|plan|build|design|architect|figure\s*out|think\s*about)|"
    r"we\s*(need|should)\s*(to|build|create|implement)|"
    r"(next\s*steps?|roadmap|sprint|milestone)|"
    r"how\s*should\s*we\s*(approach|handle|implement))",
    re.IGNORECASE,
)

CREATIVE_SIGNALS = re.compile(
    r"(write|draft|compose|create|generate|brainstorm|imagine|design)\s",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Routing Table
# ---------------------------------------------------------------------------

# Maps intent → (RAGDepth, run_precognition)
_ROUTING: dict[MessageIntent, tuple[RAGDepth, bool]] = {
    MessageIntent.GREETING:      (RAGDepth.NONE,  False),
    MessageIntent.ACKNOWLEDGMENT: (RAGDepth.NONE,  False),
    MessageIntent.FAREWELL:      (RAGDepth.NONE,  False),
    MessageIntent.EMOTIONAL:     (RAGDepth.NONE,  True),
    MessageIntent.CONTINUATION:  (RAGDepth.LIGHT, False),
    MessageIntent.CLARIFICATION: (RAGDepth.LIGHT, False),
    MessageIntent.KNOWLEDGE:     (RAGDepth.FULL,  True),
    MessageIntent.CREATIVE:      (RAGDepth.FULL,  True),
    MessageIntent.PLANNING:      (RAGDepth.FULL,  True),
    MessageIntent.META:          (RAGDepth.LIGHT, True),
    MessageIntent.COMMAND:       (RAGDepth.NONE,  False),
}


def _make_result(intent: MessageIntent, confidence: float,
                 reasoning: str) -> IntentResult:
    """Build IntentResult from intent using the routing table."""
    rag, precog = _ROUTING[intent]
    return IntentResult(
        intent=intent,
        confidence=confidence,
        rag_depth=rag,
        run_precognition=precog,
        reasoning=reasoning,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def classify_intent(
    message: str,
    conversation_turn_count: int = 0,
) -> IntentResult:
    """Classify a message's intent and return routing decisions.

    Args:
        message: The user's message text.
        conversation_turn_count: How many user turns into the conversation.
            Turn 0-1 gets slight confidence boost toward GREETING.

    Returns:
        IntentResult with intent classification and routing decisions.

    Classification order (first match wins, except EMOTIONAL which overrides):
        1. COMMAND — starts with /
        2. EMOTIONAL — emotional distress signals (always gets Pre-Cognition)
        3. GREETING — short greeting patterns (boosted on turn 0-1)
        4. ACKNOWLEDGMENT — short acknowledgment patterns
        5. FAREWELL — short farewell patterns
        6. CONTINUATION — "tell me more" patterns
        7. CLARIFICATION — "what do you mean" patterns
        8. META — questions about the system/self
        9. KNOWLEDGE — recall/search patterns
        10. PLANNING — project/work patterns
        11. CREATIVE — generative patterns
        12. Default: KNOWLEDGE (if message > 20 chars) or ACKNOWLEDGMENT
    """
    text = message.strip()

    # Short-circuit: empty messages
    if not text:
        return _make_result(MessageIntent.ACKNOWLEDGMENT, 0.9, "Empty message")

    # 1. Commands
    if COMMAND_PATTERNS.match(text):
        return _make_result(MessageIntent.COMMAND, 1.0, "Slash command detected")

    # 2. Emotional (check before greetings — "I'm feeling terrible"
    #    shouldn't match as greeting)
    if EMOTIONAL_SIGNALS.search(text):
        return _make_result(MessageIntent.EMOTIONAL, 0.8,
                            "Emotional distress signals")

    # 3-5. Short pattern matches (only for short messages)
    if len(text) < 60:
        if GREETING_PATTERNS.match(text):
            conf = 0.95 if conversation_turn_count <= 1 else 0.8
            return _make_result(MessageIntent.GREETING, conf,
                                "Greeting pattern")

        if ACK_PATTERNS.match(text):
            return _make_result(MessageIntent.ACKNOWLEDGMENT, 0.9,
                                "Acknowledgment pattern")

        if FAREWELL_PATTERNS.match(text):
            return _make_result(MessageIntent.FAREWELL, 0.9,
                                "Farewell pattern")

        if CONTINUATION_PATTERNS.match(text):
            return _make_result(MessageIntent.CONTINUATION, 0.85,
                                "Continuation pattern")

    # 6. Clarification
    if CLARIFICATION_PATTERNS.search(text):
        return _make_result(MessageIntent.CLARIFICATION, 0.8,
                            "Clarification pattern")

    # 7. Meta
    if META_PATTERNS.search(text):
        return _make_result(MessageIntent.META, 0.8,
                            "Meta/self-referential pattern")

    # 8-10. Content intents (check all, pick highest signal)
    planning_match = PLANNING_SIGNALS.search(text)
    knowledge_match = KNOWLEDGE_SIGNALS.search(text)
    creative_match = CREATIVE_SIGNALS.search(text)

    if planning_match:
        return _make_result(MessageIntent.PLANNING, 0.75,
                            "Planning signals detected")
    if knowledge_match:
        return _make_result(MessageIntent.KNOWLEDGE, 0.75,
                            "Knowledge recall signals")
    if creative_match:
        return _make_result(MessageIntent.CREATIVE, 0.7,
                            "Creative generation signals")

    # 11. Default: longer messages assumed to need knowledge
    if len(text) > 20:
        return _make_result(MessageIntent.KNOWLEDGE, 0.5,
                            "Default — substantive message")
    else:
        return _make_result(MessageIntent.ACKNOWLEDGMENT, 0.4,
                            "Default — short message")
