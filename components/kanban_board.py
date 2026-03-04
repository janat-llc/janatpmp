"""KanbanBoard — gr.HTML drag-and-drop Kanban board component.

First Needle: a custom Gradio component with api_info().
Native HTML5 drag-and-drop, zero JS libraries. Drag a card to a new column →
JS sets _pending_action + trigger('change') → Python .change() handler updates
SQLite → returns refreshed board → props.value re-renders. One component, one file.

R36: Kanban Board
R36.1: Fix server_functions (not supported on gr.HTML), use trigger('change') pattern
R36.2: Entity type filter, Done column 14-day recency cap, card click stays in Work tab
"""

import json
import logging
from datetime import datetime

import gradio as gr

from db.operations import list_items, list_tasks, update_item, update_task

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Column Definitions
# ---------------------------------------------------------------------------
# (column_id, display_title, color, [statuses_mapped], droppable)

ITEM_COLUMNS = [
    ("not_started", "Backlog",      "#6366f1", ["not_started"], True),
    ("planning",    "Planning",     "#f59e0b", ["planning"],    True),
    ("in_progress", "In Progress",  "#00FFFF", ["in_progress"], True),
    ("blocked",     "Blocked",      "#ef4444", ["blocked"],     True),
    ("review",      "Review",       "#8b5cf6", ["review"],      True),
    ("done",        "Done",         "#10b981", ["completed", "shipped"], True),
]

TASK_COLUMNS = [
    ("pending",     "Pending",      "#6366f1", ["pending"],     True),
    ("processing",  "Processing",   "#f59e0b", ["processing"],  True),
    ("review",      "Review",       "#8b5cf6", ["review"],      True),
    ("done",        "Done",         "#10b981", ["completed"],   True),
    ("failed",      "Failed",       "#666666", ["failed", "retry", "dlq"], False),
]
# No blocked column for tasks — a blocked task is a symptom of a blocked item.
# If a task can't proceed, the parent item gets blocked and the task gets failed/dlq'd.

# Entity types excluded from "All Types" board view — containers, not workable items
BOARD_EXCLUDED_TYPES = {"project", "book", "chapter"}

# Done column only shows items updated within this many days
DONE_RECENCY_DAYS = 14


# ---------------------------------------------------------------------------
# Data Helpers
# ---------------------------------------------------------------------------

def _age_days(created_at: str) -> int:
    """Compute days since creation from ISO timestamp."""
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        return max(0, (datetime.now(created.tzinfo) - created).days)
    except Exception:
        return 0


def build_board_data(view_mode: str = "items", filters: dict | None = None) -> dict:
    """Build the full board value dict from database state.

    Items view excludes container types (project, book, chapter) by default —
    override via the type filter dropdown. Done column applies 14-day recency
    cap and includes total_count for "visible / total" header display.

    Args:
        view_mode: "items" or "tasks"
        filters: Optional dict with keys: domain, type, show_archived

    Returns:
        Dict with keys: view_mode, columns, filters, selected_card
    """
    filters = filters or {}
    col_defs = TASK_COLUMNS if view_mode == "tasks" else ITEM_COLUMNS

    # Build status → column_id lookup
    status_to_col = {}
    for col_id, _, _, statuses, _ in col_defs:
        for s in statuses:
            status_to_col[s] = col_id

    # Query database
    if view_mode == "tasks":
        query_kwargs = {"limit": 200}
        if filters.get("assigned_to"):
            query_kwargs["assigned_to"] = filters["assigned_to"]
        rows = list_tasks(**query_kwargs)
    else:
        query_kwargs = {"limit": 200}
        if filters.get("domain") and filters["domain"] != "all":
            query_kwargs["domain"] = filters["domain"]
        if filters.get("type") and filters["type"] != "all":
            query_kwargs["entity_type"] = filters["type"]
        rows = list_items(**query_kwargs)
        # Exclude non-workable entity types unless user explicitly filters
        if not filters.get("type") or filters["type"] == "all":
            rows = [r for r in rows if r.get("entity_type") not in BOARD_EXCLUDED_TYPES]

    # Build column buckets
    col_cards: dict[str, list] = {col_id: [] for col_id, *_ in col_defs}
    done_total = 0  # Total done items (before recency filter) for header display

    for row in rows:
        status = row.get("status", "")

        # Skip archived unless filter says show them
        if status == "archived" and not filters.get("show_archived"):
            continue

        col_id = status_to_col.get(status)
        if col_id is None:
            # Archived items that pass the filter go to "done" column
            if status == "archived":
                col_id = "done"
            else:
                continue

        # Done column: track total count, apply recency filter
        if col_id == "done":
            done_total += 1
            updated = row.get("updated_at", "")
            if updated:
                try:
                    age_days = (datetime.now() - datetime.fromisoformat(updated)).days
                    if age_days > DONE_RECENCY_DAYS:
                        continue  # Skip old done items from visible cards
                except (ValueError, TypeError):
                    pass  # Parse failure → include the card

        age = _age_days(row.get("created_at", ""))

        if view_mode == "tasks":
            card = {
                "id": row["id"],
                "title": (row.get("title", "") or "")[:60],
                "task_type": row.get("task_type", ""),
                "priority": row.get("priority", "normal"),
                "assigned_to": row.get("assigned_to", ""),
                "age_days": age,
                "created_by": row.get("created_by", "unknown"),
            }
        else:
            card = {
                "id": row["id"],
                "title": (row.get("title", "") or "")[:60],
                "entity_type": row.get("entity_type", ""),
                "priority": row.get("priority", 3),
                "domain": row.get("domain", ""),
                "age_days": age,
                "created_by": row.get("created_by", "unknown"),
            }

        col_cards[col_id].append(card)

    # Assemble columns — hide empty columns except primary intake/completion
    ALWAYS_VISIBLE = {"not_started", "done", "pending"}
    columns = []
    for col_id, title, color, _statuses, droppable in col_defs:
        cards = col_cards.get(col_id, [])
        if col_id not in ALWAYS_VISIBLE and not cards:
            continue
        columns.append({
            "id": col_id,
            "title": title,
            "color": color,
            "droppable": droppable,
            "cards": cards,
        })

    # Inject total_count for done column header ("7 / 67" display)
    for col in columns:
        if col["id"] == "done":
            col["total_count"] = done_total

    return {
        "view_mode": view_mode,
        "columns": columns,
        "filters": {
            "domain": filters.get("domain", "all"),
            "type": filters.get("type", "all"),
            "show_archived": bool(filters.get("show_archived")),
        },
        "selected_card": None,
    }


# ---------------------------------------------------------------------------
# Action Handlers (called from Python .change() listener via _pending_action)
# ---------------------------------------------------------------------------

def move_card(card_id: str, new_column_id: str, view_mode: str, filters_json: str) -> dict:
    """JS drop handler calls this. Updates DB status, returns refreshed board."""
    try:
        filters = json.loads(filters_json) if filters_json else {}
    except (json.JSONDecodeError, TypeError):
        filters = {}

    # Map column_id → actual status value (first status in the column's list)
    col_defs = TASK_COLUMNS if view_mode == "tasks" else ITEM_COLUMNS
    target_statuses = {c[0]: c[3][0] for c in col_defs if c[4]}  # only droppable
    new_status = target_statuses.get(new_column_id)

    if not new_status:
        logger.debug("move_card: invalid target column %s", new_column_id)
        return build_board_data(view_mode, filters)

    try:
        if view_mode == "tasks":
            update_task(card_id, status=new_status, actor="mat")
        else:
            update_item(card_id, status=new_status, actor="mat")
        logger.debug("move_card: %s → %s (%s)", card_id[:8], new_status, view_mode)
    except Exception as e:
        logger.warning("move_card failed: %s", e)

    return build_board_data(view_mode, filters)


def refresh_board(view_mode: str, filters_json: str) -> dict:
    """JS filter change or timer calls this. Returns fresh board data."""
    try:
        filters = json.loads(filters_json) if filters_json else {}
    except (json.JSONDecodeError, TypeError):
        filters = {}
    return build_board_data(view_mode, filters)


# ---------------------------------------------------------------------------
# HTML Template
# ---------------------------------------------------------------------------

KANBAN_HTML = """
<div class="kanban-wrapper">
    <div class="kanban-toolbar">
        <div class="view-toggle">
            <button class="view-btn ${value.view_mode === 'items' ? 'active' : ''}"
                    data-view="items">Items</button>
            <button class="view-btn ${value.view_mode === 'tasks' ? 'active' : ''}"
                    data-view="tasks">Tasks</button>
        </div>
        <div class="kanban-filters">
            ${value.view_mode === 'items' ? `
                <select class="filter-control filter-domain">
                    <option value="all" ${value.filters.domain === 'all' ? 'selected' : ''}>All Domains</option>
                </select>
                <select class="filter-control filter-type">
                    <option value="all" ${value.filters.type === 'all' ? 'selected' : ''}>All Types</option>
                </select>
            ` : `
                <select class="filter-control filter-assigned">
                    <option value="all">All Assigned</option>
                </select>
            `}
            <label class="archive-toggle">
                <input type="checkbox" class="filter-archived"
                       ${value.filters.show_archived ? 'checked' : ''} />
                <span>Archived</span>
            </label>
        </div>
        <div class="kanban-stats">
            ${(() => {
                const cols = value.columns || [];
                const total = cols.reduce((s, c) => s + c.cards.length, 0);
                return '<span class="stat-pill">' + total + ' cards</span>';
            })()}
        </div>
    </div>

    <div class="kanban-board">
        ${(value.columns || []).map(col => `
            <div class="kanban-column ${col.droppable ? '' : 'no-drop'}"
                 data-col-id="${col.id}">
                <div class="column-header" style="border-top: 3px solid ${col.color}">
                    <span class="col-title">${col.title}</span>
                    <span class="col-count" style="background: ${col.color}22; color: ${col.color}">
                        ${col.total_count != null ? col.cards.length + ' / ' + col.total_count : col.cards.length}
                    </span>
                </div>
                <div class="card-list" data-col-id="${col.id}"
                     data-droppable="${col.droppable}">
                    ${col.cards.map(card => `
                        <div class="kanban-card" draggable="${col.droppable}"
                             data-card-id="${card.id}">
                            <div class="card-priority priority-${
                                value.view_mode === 'items'
                                    ? (card.priority <= 1 ? 'p1' : card.priority <= 2 ? 'p2' : 'p3')
                                    : card.priority
                            }"></div>
                            <div class="card-body">
                                <div class="card-title">${card.title}</div>
                                <div class="card-meta">
                                    <span class="card-badge">${
                                        value.view_mode === 'items'
                                            ? (card.entity_type || '').replace('_', ' ')
                                            : (card.task_type || '').replace('_', ' ')
                                    }</span>
                                    <span class="card-secondary">${
                                        value.view_mode === 'items'
                                            ? (card.domain || '')
                                            : (card.assigned_to || '')
                                    }</span>
                                    ${card.age_days > 0
                                        ? '<span class="card-age">' + card.age_days + 'd</span>'
                                        : ''
                                    }
                                    ${card.created_by && card.created_by !== 'unknown'
                                        ? '<span class="card-actor actor-' + card.created_by + '">' + card.created_by[0].toUpperCase() + '</span>'
                                        : ''
                                    }
                                </div>
                            </div>
                        </div>
                    `).join('')}
                    ${col.cards.length === 0
                        ? '<div class="empty-col">No cards</div>'
                        : ''
                    }
                </div>
            </div>
        `).join('')}
    </div>
</div>
"""


# ---------------------------------------------------------------------------
# CSS Template
# ---------------------------------------------------------------------------

KANBAN_CSS = """
    .kanban-wrapper {
        background: #0a0a0a;
        border-radius: 12px;
        padding: 16px;
        font-family: 'Rajdhani', sans-serif;
        color: #e0e0e0;
        overflow-x: auto;
    }

    /* --- Toolbar --- */
    .kanban-toolbar {
        display: flex;
        align-items: center;
        gap: 16px;
        margin-bottom: 16px;
        flex-wrap: wrap;
    }
    .view-toggle {
        display: flex;
        gap: 0;
        border: 1px solid #333;
        border-radius: 8px;
        overflow: hidden;
    }
    .view-btn {
        background: #111;
        border: none;
        color: #808080;
        padding: 6px 16px;
        font-family: 'Orbitron', 'Rajdhani', sans-serif;
        font-size: 12px;
        font-weight: 600;
        letter-spacing: 0.5px;
        cursor: pointer;
        transition: all 0.15s;
    }
    .view-btn.active {
        background: #00FFFF22;
        color: #00FFFF;
    }
    .view-btn:hover:not(.active) {
        background: #1a1a1a;
        color: #b3b3b3;
    }

    .kanban-filters {
        display: flex;
        align-items: center;
        gap: 8px;
        flex: 1;
    }
    .filter-control {
        background: #111;
        border: 1px solid #333;
        border-radius: 8px;
        color: #b3b3b3;
        padding: 5px 10px;
        font-family: 'Rajdhani', sans-serif;
        font-size: 13px;
        cursor: pointer;
        outline: none;
    }
    .filter-control:focus {
        border-color: #00FFFF;
    }
    .archive-toggle {
        display: flex;
        align-items: center;
        gap: 4px;
        color: #808080;
        font-size: 13px;
        cursor: pointer;
    }
    .archive-toggle input {
        accent-color: #00FFFF;
    }
    .kanban-stats {
        margin-left: auto;
    }
    .stat-pill {
        background: #111;
        border: 1px solid #333;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 12px;
        color: #808080;
        font-weight: 500;
    }

    /* --- Board --- */
    .kanban-board {
        display: flex;
        gap: 12px;
        min-height: 350px;
        padding-bottom: 8px;
    }

    /* --- Columns --- */
    .kanban-column {
        background: #111111;
        border-radius: 10px;
        min-width: 190px;
        max-width: 280px;
        flex: 1;
        display: flex;
        flex-direction: column;
    }
    .kanban-column.no-drop {
        opacity: 0.6;
    }
    .column-header {
        padding: 12px 12px 8px;
        display: flex;
        justify-content: space-between;
        align-items: center;
        border-radius: 10px 10px 0 0;
        user-select: none;
    }
    .col-title {
        font-family: 'Orbitron', 'Rajdhani', sans-serif;
        font-weight: 600;
        font-size: 12px;
        letter-spacing: 0.5px;
        text-transform: uppercase;
    }
    .col-count {
        min-width: 24px;
        height: 24px;
        border-radius: 12px;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 11px;
        font-weight: 700;
    }

    /* --- Card List (drop zone) --- */
    .card-list {
        flex: 1;
        padding: 6px 8px;
        min-height: 60px;
        transition: background 0.2s;
        border-radius: 0 0 10px 10px;
    }
    .card-list.drag-over {
        background: rgba(0, 255, 255, 0.05);
    }
    .empty-col {
        color: #4d4d4d;
        font-size: 12px;
        text-align: center;
        padding: 24px 8px;
        border: 1px dashed #333;
        border-radius: 8px;
        margin: 4px;
    }

    /* --- Cards --- */
    .kanban-card {
        background: #1a1a1a;
        border: 1px solid #333;
        border-radius: 8px;
        padding: 10px 10px 10px 14px;
        margin-bottom: 6px;
        cursor: grab;
        transition: all 0.15s ease;
        position: relative;
        overflow: hidden;
    }
    .kanban-card:hover {
        border-color: #00FFFF;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
    }
    .kanban-card.dragging {
        opacity: 0.4;
        transform: rotate(1deg) scale(0.97);
    }

    /* Priority stripe */
    .card-priority {
        width: 3px;
        height: 100%;
        position: absolute;
        left: 0;
        top: 0;
        border-radius: 8px 0 0 8px;
    }
    .priority-p1 { background: #ef4444; }
    .priority-p2 { background: #f59e0b; }
    .priority-p3 { background: #888888; }
    .priority-urgent { background: #ef4444; }
    .priority-normal { background: #888888; }
    .priority-background { background: #444444; }

    .card-body {
        padding-left: 4px;
    }
    .card-title {
        font-size: 13px;
        line-height: 1.4;
        color: #e0e0e0;
        margin-bottom: 6px;
    }
    .card-meta {
        display: flex;
        align-items: center;
        gap: 6px;
        flex-wrap: wrap;
    }
    .card-badge {
        background: rgba(0, 255, 255, 0.1);
        color: #80ffff;
        padding: 1px 8px;
        border-radius: 8px;
        font-size: 10px;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.3px;
    }
    .card-secondary {
        color: #808080;
        font-size: 11px;
    }
    .card-age {
        color: #4d4d4d;
        font-size: 10px;
        margin-left: auto;
    }
    .card-actor {
        display: inline-block;
        width: 18px; height: 18px;
        border-radius: 50%;
        text-align: center;
        font-size: 10px;
        line-height: 18px;
        font-family: 'Orbitron', monospace;
        font-weight: bold;
        margin-left: 4px;
    }
    .actor-mat { background: #00FFFF22; color: #00FFFF; border: 1px solid #00FFFF44; }
    .actor-claude { background: #D4A76A22; color: #D4A76A; border: 1px solid #D4A76A44; }
    .actor-janus { background: #FF00FF22; color: #FF00FF; border: 1px solid #FF00FF44; }
    .actor-agent { background: #88888822; color: #888888; border: 1px solid #88888844; }
    .actor-imported { background: #44444422; color: #666666; border: 1px solid #44444444; }
    .actor-unknown { display: none; }

    /* --- Animations --- */
    @keyframes cardIn {
        from { opacity: 0; transform: translateY(-6px); }
        to { opacity: 1; transform: translateY(0); }
    }
    .kanban-card {
        animation: cardIn 0.15s ease;
    }
"""


# ---------------------------------------------------------------------------
# JS Template
# ---------------------------------------------------------------------------

KANBAN_JS = """
    let dragSrcCardId = null;
    let isDragging = false;

    // ── Drag & Drop ──────────────────────────────
    element.addEventListener('dragstart', (e) => {
        const card = e.target.closest('.kanban-card');
        if (!card) return;
        dragSrcCardId = card.dataset.cardId;
        isDragging = true;
        card.classList.add('dragging');
        e.dataTransfer.effectAllowed = 'move';
    });

    element.addEventListener('dragend', (e) => {
        isDragging = false;
        const card = e.target.closest('.kanban-card');
        if (card) card.classList.remove('dragging');
        element.querySelectorAll('.card-list').forEach(cl =>
            cl.classList.remove('drag-over')
        );
    });

    element.addEventListener('dragover', (e) => {
        const cardList = e.target.closest('.card-list');
        if (!cardList || cardList.dataset.droppable !== 'true') return;
        e.preventDefault();
        cardList.classList.add('drag-over');
    });

    element.addEventListener('dragleave', (e) => {
        const cardList = e.target.closest('.card-list');
        if (cardList && !cardList.contains(e.relatedTarget)) {
            cardList.classList.remove('drag-over');
        }
    });

    element.addEventListener('drop', (e) => {
        e.preventDefault();
        const cardList = e.target.closest('.card-list');
        if (!cardList || !dragSrcCardId) return;
        if (cardList.dataset.droppable !== 'true') return;
        cardList.classList.remove('drag-over');

        const newColumnId = cardList.dataset.colId;
        const nv = JSON.parse(JSON.stringify(props.value));
        nv._pending_action = {
            type: 'move',
            card_id: dragSrcCardId,
            new_column: newColumnId
        };
        props.value = nv;
        trigger('change');

        dragSrcCardId = null;
    });

    // ── View Mode Toggle ─────────────────────────
    element.addEventListener('click', (e) => {
        const btn = e.target.closest('.view-btn');
        if (!btn || btn.classList.contains('active')) return;

        const newViewMode = btn.dataset.view;
        const nv = JSON.parse(JSON.stringify(props.value));
        nv._pending_action = {
            type: 'refresh',
            view_mode: newViewMode,
            filters: nv.filters || {}
        };
        props.value = nv;
        trigger('change');
    });

    // ── Filter Controls ──────────────────────────
    element.addEventListener('change', (e) => {
        const control = e.target.closest('.filter-control, .filter-archived');
        if (!control) return;

        const filters = Object.assign({}, props.value.filters || {});
        if (control.classList.contains('filter-domain')) {
            filters.domain = control.value;
        } else if (control.classList.contains('filter-type')) {
            filters.type = control.value;
        } else if (control.classList.contains('filter-assigned')) {
            filters.assigned_to = control.value === 'all' ? '' : control.value;
        } else if (control.classList.contains('filter-archived')) {
            filters.show_archived = control.checked;
        }

        const nv = JSON.parse(JSON.stringify(props.value));
        nv._pending_action = {
            type: 'refresh',
            view_mode: nv.view_mode || 'items',
            filters: filters
        };
        nv.filters = filters;
        props.value = nv;
        trigger('change');
    });

    // ── Card Click → Select ──────────────────────
    element.addEventListener('click', (e) => {
        if (isDragging) return;
        const card = e.target.closest('.kanban-card');
        if (!card) return;

        const nv = JSON.parse(JSON.stringify(props.value));
        nv.selected_card = card.dataset.cardId;
        props.value = nv;
        trigger('select');
    });
"""


# ---------------------------------------------------------------------------
# Component Class
# ---------------------------------------------------------------------------

class KanbanBoard(gr.HTML):
    """Drag-and-drop Kanban board for items and tasks.

    First Needle — custom Gradio component with api_info().
    JS uses _pending_action + trigger('change') for Python callbacks.
    Value shape: {view_mode, columns, filters, selected_card, _pending_action?}
    """

    def __init__(self, value=None, **kwargs):
        if value is None:
            value = build_board_data("items")
        super().__init__(
            value=value,
            html_template=KANBAN_HTML,
            css_template=KANBAN_CSS,
            js_on_load=KANBAN_JS,
            **kwargs,
        )

    def api_info(self):
        return {
            "type": "object",
            "description": "Kanban board state with columns and cards",
            "properties": {
                "view_mode": {"type": "string", "enum": ["items", "tasks"]},
                "columns": {"type": "array", "items": {"type": "object"}},
                "filters": {"type": "object"},
                "selected_card": {"type": "string"},
            },
        }
