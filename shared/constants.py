"""Shared constants for JANATPMP — enum lists, magic numbers, defaults."""

# --- Entity enum lists (used by UI dropdowns and validation) ---

PROJECT_TYPES = ["project", "epic", "book", "website", "milestone"]

ALL_TYPES = [
    "project", "epic", "feature", "component", "milestone",
    "book", "chapter", "section",
    "website", "page", "deployment",
    "social_campaign", "speaking_event", "life_area",
]

STATUSES = [
    "not_started", "planning", "in_progress", "blocked",
    "review", "completed", "shipped", "archived",
]

TASK_STATUSES = [
    "pending", "processing", "blocked", "review",
    "completed", "failed", "retry", "dlq",
]

TASK_TYPES = [
    "agent_story", "user_story", "subtask",
    "research", "review", "documentation",
]

ASSIGNEES = ["unassigned", "agent", "claude", "mat", "janus"]

PRIORITIES = ["urgent", "normal", "background"]

DOC_TYPES = [
    "conversation", "file", "artifact", "research",
    "agent_output", "session_notes", "code",
]

DOC_SOURCES = [
    "claude_exporter", "upload", "agent", "generated", "manual",
]

# --- Chat defaults ---

MAX_TOOL_ITERATIONS = 10
MAX_TOOL_RESULT_CHARS = 4000

RAG_SCORE_THRESHOLD = 0.4

DEFAULT_CHAT_HISTORY = [{
    "role": "assistant",
    "content": "How can I help you today?",
}]
