"""Admin page — configuration, persona, and platform operations.

Sovereign page at /admin with 3 tabs:
  Settings   — platform settings editor grouped by category
  Persona    — user identity, location, preferences
  Operations — backup/restore, logs, health, lifecycle

Three-panel layout:
  Left sidebar: context per active tab (categories / identity card / health)
  Center: editors, controls, logs
  Right sidebar: Janus quick-chat (shared/chat_sidebar.py)

Can run standalone: python pages/admin.py

Deep link hook (future, not implemented):
  /admin?tab=settings&category=rag → navigate directly to RAG settings
"""

import json
import logging
from datetime import date
import gradio as gr
import pandas as pd
from db.operations import (
    backup_database, restore_database, reset_database, list_backups,
    get_stats, get_schema_info, export_platform_data, import_platform_data,
)
from services.settings import get_setting, set_setting, get_settings_by_category
from shared.chat_sidebar import build_chat_sidebar, wire_chat_sidebar

logger = logging.getLogger(__name__)


def _calculate_age(birthdate_str: str) -> int | None:
    """Calculate age from ISO birthdate string (YYYY-MM-DD)."""
    try:
        bd = date.fromisoformat(birthdate_str)
        today = date.today()
        return today.year - bd.year - ((today.month, today.day) < (bd.month, bd.day))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SETTING_CATEGORIES = [
    ("chat", "Platform Defaults"),
    ("ollama", "Ollama / Model Config"),
    ("rag", "RAG Configuration"),
    ("ingestion", "Ingestion Paths"),
    ("export", "Export"),
    ("system", "System"),
]

# Keys that are internal / not user-editable
_HIDDEN_KEYS = {"janus_conversation_id"}


def _backups_to_df():
    backups = list_backups()
    if not backups:
        return pd.DataFrame(columns=["Name", "Size (KB)", "Stores", "Created"])
    return pd.DataFrame([{
        "Name": b["name"],
        "Size (KB)": round(b["size"] / 1024, 1),
        "Stores": b.get("stores", "SQLite only"),
        "Created": b["created"][:19],
    } for b in backups])


def _backup_names():
    return [b["name"] for b in list_backups()]


def _load_health_stats():
    """Load platform health stats for the Operations sidebar."""
    health = {}
    try:
        stats = get_stats()
        health["Items"] = stats.get("total_items", 0)
        health["Tasks"] = stats.get("total_tasks", 0)
        health["Documents"] = stats.get("total_documents", 0)
        health["Relationships"] = stats.get("total_relationships", 0)
    except Exception:
        pass

    try:
        from db.operations import get_connection
        with get_connection() as conn:
            health["Conversations"] = conn.execute(
                "SELECT COUNT(*) FROM conversations"
            ).fetchone()[0]
            health["Messages"] = conn.execute(
                "SELECT COUNT(*) FROM messages"
            ).fetchone()[0]
            health["Chunks"] = conn.execute(
                "SELECT COUNT(*) FROM chunks"
            ).fetchone()[0]
            health["Files Tracked"] = conn.execute(
                "SELECT COUNT(*) FROM file_registry"
            ).fetchone()[0]
    except Exception:
        pass

    return health


# ---------------------------------------------------------------------------
# Page builder
# ---------------------------------------------------------------------------

def build_admin_page():
    """Build the sovereign Admin page layout. Call inside a gr.Blocks context."""

    # === STATES ===
    active_tab = gr.State("Settings")
    selected_category = gr.State("chat")

    # === RIGHT SIDEBAR (Janus quick-chat) ===
    chatbot, chat_input, chat_history, sidebar_conv_id = build_chat_sidebar()

    # === CENTER TABS ===
    with gr.Tabs(elem_id="admin-tabs") as admin_tabs:

        # ---------------------------------------------------------------
        # TAB 1: Settings
        # ---------------------------------------------------------------
        with gr.Tab("Settings") as settings_tab:
            with gr.Row():
                # --- Left panel: category selector ---
                with gr.Column(scale=1, min_width=220):
                    gr.Markdown("### Setting Categories")
                    for cat_key, cat_label in SETTING_CATEGORIES:
                        cat_btn = gr.Button(
                            cat_label, size="sm",
                            variant="secondary",
                            key=f"cat-{cat_key}",
                        )

                        def _select_cat(k=cat_key):
                            return k

                        cat_btn.click(
                            _select_cat,
                            outputs=[selected_category],
                            api_visibility="private",
                            key=f"cat-click-{cat_key}",
                        )

                # --- Right panel: settings editor ---
                with gr.Column(scale=3):
                    settings_header = gr.Markdown("### Platform Defaults")

                    @gr.render(inputs=[selected_category])
                    def render_settings(category):
                        cat_label = dict(SETTING_CATEGORIES).get(
                            category, category
                        )
                        gr.Markdown(
                            f"### {cat_label}",
                            key=f"settings-header-{category}",
                        )

                        settings = get_settings_by_category(category)
                        if not settings:
                            gr.Markdown(
                                "*No settings in this category.*",
                                key=f"settings-empty-{category}",
                            )
                            return

                        # Build editable fields for each setting
                        inputs_map = {}
                        for key, value in settings.items():
                            if key in _HIDDEN_KEYS:
                                continue
                            # Use human-readable label
                            label = key.replace("_", " ").title()
                            if key == "chat_provider":
                                txt = gr.Dropdown(
                                    choices=["anthropic", "gemini", "ollama"],
                                    value=str(value) if value else "ollama",
                                    label=label, interactive=True,
                                    key=f"setting-{key}",
                                )
                            elif key == "chat_model":
                                from services.chat import fetch_ollama_models
                                _models = fetch_ollama_models() or ([str(value)] if value else [])
                                txt = gr.Dropdown(
                                    choices=_models,
                                    value=str(value) if value else "",
                                    label=label, interactive=True,
                                    allow_custom_value=True,
                                    key=f"setting-{key}",
                                )
                            else:
                                txt = gr.Textbox(
                                    label=label,
                                    value=str(value) if value else "",
                                    interactive=True,
                                    key=f"setting-{key}",
                                )
                            inputs_map[key] = txt

                        if inputs_map:
                            save_btn = gr.Button(
                                f"Save {cat_label}",
                                variant="primary",
                                key=f"save-{category}",
                            )
                            save_status = gr.Textbox(
                                show_label=False,
                                interactive=False,
                                key=f"save-status-{category}",
                            )

                            def _save_settings(
                                *values, keys=list(inputs_map.keys())
                            ):
                                errors = []
                                for k, v in zip(keys, values):
                                    err = set_setting(k, v)
                                    if err:
                                        errors.append(f"{k}: {err}")
                                if errors:
                                    return "Errors: " + "; ".join(errors)
                                return f"Saved {len(keys)} settings."

                            save_btn.click(
                                _save_settings,
                                inputs=list(inputs_map.values()),
                                outputs=[save_status],
                                api_visibility="private",
                                key=f"save-click-{category}",
                            )

        # ---------------------------------------------------------------
        # TAB 2: Persona
        # ---------------------------------------------------------------
        with gr.Tab("Persona") as persona_tab:
            # Load initial family from settings
            _init_family = []
            try:
                _init_family = json.loads(
                    get_setting("user_family") or "[]"
                )
            except Exception:
                pass
            family_state = gr.State(_init_family)

            gr.Markdown("### User Persona")
            gr.Markdown(
                "Configure what Janus knows about you. Only non-empty "
                "fields appear in the system prompt context block."
            )

            # --- Identity ---
            gr.Markdown("#### Identity")
            with gr.Row():
                persona_full_name = gr.Textbox(
                    label="Full Name",
                    value=get_setting("user_full_name") or "",
                    placeholder="e.g. Mat Gallagher",
                    interactive=True, scale=2,
                )
                persona_preferred = gr.Textbox(
                    label="Preferred Name",
                    value=get_setting("user_preferred_name") or "Mat",
                    interactive=True, scale=1,
                )
                persona_birthdate = gr.Textbox(
                    label="Birthdate (YYYY-MM-DD)",
                    value=get_setting("user_birthdate") or "",
                    placeholder="1985-06-15",
                    interactive=True, scale=1,
                )

            # --- Location ---
            gr.Markdown("#### Location")
            persona_location = gr.Textbox(
                label="Full Address",
                value=get_setting("location_name") or "",
                interactive=True,
            )
            with gr.Row():
                persona_lat = gr.Textbox(
                    label="Latitude",
                    value=get_setting("location_lat") or "",
                    interactive=True,
                )
                persona_lon = gr.Textbox(
                    label="Longitude",
                    value=get_setting("location_lon") or "",
                    interactive=True,
                )
                persona_tz = gr.Textbox(
                    label="Timezone (IANA)",
                    value=get_setting("location_tz") or "",
                    interactive=True,
                )

            # --- Family ---
            gr.Markdown("#### Family")

            @gr.render(inputs=[family_state])
            def render_family(members):
                if not members:
                    gr.Markdown(
                        "*No family members added.*", key="fam-empty"
                    )
                for i, member in enumerate(members):
                    name = member.get("name", "")
                    relation = member.get("relation", "")
                    bd = member.get("birthdate", "")
                    age_str = ""
                    if bd:
                        age = _calculate_age(bd)
                        if age is not None:
                            age_str = f" (age {age})"
                    with gr.Row(key=f"fam-{i}"):
                        gr.Markdown(
                            f"**{name}** \u2014 {relation}{age_str}"
                            + (f", born {bd}" if bd else ""),
                            key=f"fam-text-{i}",
                        )
                        rm_btn = gr.Button(
                            "Remove", variant="stop", size="sm",
                            scale=0, key=f"fam-rm-{i}",
                        )

                        def _remove(idx=i, cur=members):
                            updated = list(cur)
                            del updated[idx]
                            return updated

                        rm_btn.click(
                            _remove, outputs=[family_state],
                            api_visibility="private",
                            key=f"fam-rm-click-{i}",
                        )

            with gr.Row():
                fam_name_input = gr.Textbox(
                    label="Name", scale=2, interactive=True,
                )
                fam_rel_input = gr.Dropdown(
                    label="Relation",
                    choices=[
                        "spouse", "child", "parent", "sibling", "other",
                    ],
                    value="spouse", allow_custom_value=True,
                    scale=1, interactive=True,
                )
                fam_bd_input = gr.Textbox(
                    label="Birthdate (YYYY-MM-DD)", scale=1,
                    interactive=True,
                )
                fam_add_btn = gr.Button(
                    "Add", variant="primary", size="sm", scale=0,
                )

            # --- Work ---
            gr.Markdown("#### Work")
            with gr.Row():
                persona_employer = gr.Textbox(
                    label="Employer",
                    value=get_setting("user_employer") or "",
                    interactive=True,
                )
                persona_title = gr.Textbox(
                    label="Title / Role",
                    value=get_setting("user_title") or "",
                    interactive=True,
                )

            # --- Health ---
            gr.Markdown("#### Health")
            gr.Markdown(
                "*Sensitive \u2014 included in prompt with framing: "
                '"handle with care, never surface casually."*'
            )
            persona_health = gr.Textbox(
                label="Health Notes",
                value=get_setting("user_health_notes") or "",
                lines=2, interactive=True,
            )

            # --- Interests & Values ---
            gr.Markdown("#### Interests & Values")
            persona_interests = gr.Textbox(
                label="Interests",
                value=get_setting("user_interests") or "",
                placeholder="consciousness architecture, AI, literature...",
                interactive=True,
            )
            persona_values = gr.Textbox(
                label="Values",
                value=get_setting("user_values") or "",
                placeholder="sovereignty, craftsmanship, honesty...",
                interactive=True,
            )

            # --- Bio ---
            gr.Markdown("#### Bio")
            persona_bio = gr.Textbox(
                label="Anything else Janus should know?",
                value=get_setting("user_bio") or "",
                lines=3, interactive=True,
            )

            with gr.Row():
                persona_save_btn = gr.Button(
                    "Save Persona", variant="primary"
                )
                persona_status = gr.Textbox(
                    show_label=False, interactive=False, scale=2
                )

        # ---------------------------------------------------------------
        # TAB 3: Operations
        # ---------------------------------------------------------------
        with gr.Tab("Operations") as operations_tab:
            with gr.Row():
                # --- Left panel: health dashboard ---
                with gr.Column(scale=1, min_width=220):
                    gr.Markdown("### Platform Health")

                    @gr.render(inputs=[active_tab])
                    def render_ops_sidebar(_tab):
                        health = _load_health_stats()
                        for label, count in health.items():
                            gr.Markdown(
                                f"**{label}:** {count:,}",
                                key=f"ops-stat-{label.lower().replace(' ', '-')}",
                            )

                        # Last backup
                        try:
                            backups = list_backups()
                            if backups:
                                gr.Markdown(
                                    f"**Last Backup:** {backups[0]['created'][:16]}",
                                    key="ops-last-backup",
                                )
                        except Exception:
                            pass

                # --- Right panel: operations ---
                with gr.Column(scale=3):
                    # Backup & Restore
                    with gr.Accordion("Backup & Restore", open=True):
                        gr.Markdown("### Backup & Restore")
                        with gr.Row():
                            backup_btn = gr.Button(
                                "Backup Now", variant="primary"
                            )
                            db_status_msg = gr.Textbox(
                                label="Status", interactive=False, scale=2
                            )
                        backups_table = gr.DataFrame(
                            value=_backups_to_df(),
                            interactive=False, label="Available Backups"
                        )
                        with gr.Row():
                            restore_dropdown = gr.Dropdown(
                                label="Select Backup",
                                choices=_backup_names(),
                                allow_custom_value=True,
                                scale=2,
                            )
                            restore_btn = gr.Button(
                                "Restore Selected Backup", scale=1
                            )

                    # Portable Export / Import
                    with gr.Accordion("Portable Export / Import", open=False):
                        with gr.Row():
                            with gr.Column(scale=1):
                                gr.Markdown("### Export")
                                gr.Markdown(
                                    "Export project data (domains, items, tasks, "
                                    "relationships) to versioned JSON."
                                )
                                export_btn = gr.Button(
                                    "Export Project Data", variant="primary"
                                )
                                export_status = gr.Textbox(
                                    label="Export Status", interactive=False
                                )
                            with gr.Column(scale=1):
                                gr.Markdown("### Import")
                                import_path = gr.Textbox(
                                    label="Export File Path",
                                    placeholder="/app/db/exports/...",
                                    interactive=True,
                                )
                                import_btn = gr.Button(
                                    "Import Platform Data", variant="primary"
                                )
                                import_status = gr.Textbox(
                                    label="Import Status", interactive=False
                                )

                    # Database Reset
                    with gr.Accordion("Database Reset", open=False):
                        gr.Markdown(
                            "Full platform reset — wipes **SQLite**, **Qdrant** "
                            "vectors, and **Neo4j** graph. SQLite backup created "
                            "automatically. Re-run ingestion + embedding after reset."
                        )
                        with gr.Row():
                            reset_btn = gr.Button(
                                "Reset Database", variant="stop"
                            )
                            reset_status = gr.Textbox(
                                label="Reset Status", interactive=False, scale=2
                            )

                    # Application Logs
                    with gr.Accordion("Application Logs", open=False):
                        with gr.Row():
                            log_level_filter = gr.Dropdown(
                                label="Level",
                                choices=[
                                    "", "DEBUG", "INFO", "WARNING",
                                    "ERROR", "CRITICAL",
                                ],
                                value="", interactive=True, scale=1,
                            )
                            log_module_filter = gr.Textbox(
                                label="Module Filter",
                                placeholder="e.g. chat, settings",
                                value="", interactive=True, scale=2,
                            )
                            log_refresh_btn = gr.Button(
                                "Refresh", variant="primary", scale=0
                            )
                        log_table = gr.DataFrame(
                            value=pd.DataFrame(
                                columns=[
                                    "timestamp", "level", "module",
                                    "function", "message",
                                ]
                            ),
                            interactive=False, label="Recent Logs", wrap=True,
                        )

                    # Schema Info
                    with gr.Accordion("Schema Info", open=False):
                        schema_display = gr.JSON(label="Schema", value={})
                        schema_refresh_btn = gr.Button(
                            "Refresh", variant="secondary", size="sm"
                        )

                    # Lifecycle State (placeholder)
                    with gr.Accordion("Lifecycle State", open=False):
                        gr.Markdown(
                            "Coming in R19 — Bootstrap Lifecycle state machine "
                            "(CONFIGURING → SLEEPING → AWAKE)."
                        )

    # === LEFT SIDEBAR ===
    with gr.Sidebar(position="left"):
        @gr.render(inputs=[active_tab, selected_category])
        def render_left(tab, category):
            if tab == "Settings":
                gr.Markdown("### Settings")
                for cat_key, cat_label in SETTING_CATEGORIES:
                    is_active = (cat_key == category)
                    btn = gr.Button(
                        cat_label,
                        size="sm",
                        variant="primary" if is_active else "secondary",
                        key=f"sidebar-cat-{cat_key}",
                    )

                    def _sel(k=cat_key):
                        return k

                    btn.click(
                        _sel,
                        outputs=[selected_category],
                        api_visibility="private",
                        key=f"sidebar-cat-click-{cat_key}",
                    )

            elif tab == "Persona":
                gr.Markdown("### Identity")
                full_name = get_setting("user_full_name") or ""
                preferred = get_setting("user_preferred_name") or "Mat"
                display_name = full_name or preferred
                employer = get_setting("user_employer") or ""
                title = get_setting("user_title") or ""
                loc = get_setting("location_name") or "Unknown"
                tz = get_setting("location_tz") or "Unknown"

                work_line = ""
                if title and employer:
                    work_line = f"{title} at {employer}"
                elif title:
                    work_line = title
                elif employer:
                    work_line = employer

                card_parts = [f"**{display_name}**"]
                if work_line:
                    card_parts.append(work_line)
                card_parts.append(loc)
                card_parts.append(f"Timezone: {tz}")
                gr.Markdown(
                    "\n\n".join(card_parts),
                    key="sidebar-persona-card",
                )

            elif tab == "Operations":
                gr.Markdown("### Platform Health")
                health = _load_health_stats()
                for label, count in health.items():
                    gr.Markdown(
                        f"**{label}:** {count:,}",
                        key=f"sidebar-ops-{label.lower().replace(' ', '-')}",
                    )

    # === EVENT WIRING ===

    # --- Tab tracking ---
    settings_tab.select(
        lambda: "Settings", outputs=[active_tab], api_visibility="private"
    )
    persona_tab.select(
        lambda: "Persona", outputs=[active_tab], api_visibility="private"
    )
    operations_tab.select(
        lambda: "Operations", outputs=[active_tab], api_visibility="private"
    )

    # --- Family add ---
    def _add_family_member(name, relation, birthdate, current_family):
        if not name or not name.strip():
            return current_family, "", "spouse", ""
        new = {
            "name": name.strip(),
            "relation": relation or "spouse",
            "birthdate": birthdate.strip() if birthdate else "",
        }
        return current_family + [new], "", "spouse", ""

    fam_add_btn.click(
        _add_family_member,
        inputs=[fam_name_input, fam_rel_input, fam_bd_input, family_state],
        outputs=[family_state, fam_name_input, fam_rel_input, fam_bd_input],
        api_visibility="private",
    )

    # --- Persona save ---
    def _save_persona(
        full_name, preferred, birthdate, location, lat, lon, tz,
        employer, title, health, interests, values, bio, family,
    ):
        errors = []
        for key, val in [
            ("user_full_name", full_name),
            ("user_preferred_name", preferred),
            ("user_birthdate", birthdate),
            ("location_name", location),
            ("location_lat", lat),
            ("location_lon", lon),
            ("location_tz", tz),
            ("user_employer", employer),
            ("user_title", title),
            ("user_health_notes", health),
            ("user_interests", interests),
            ("user_values", values),
            ("user_bio", bio),
        ]:
            err = set_setting(key, val.strip() if val else "")
            if err:
                errors.append(f"{key}: {err}")
        # Save family as JSON
        err = set_setting("user_family", json.dumps(family or []))
        if err:
            errors.append(f"user_family: {err}")
        if errors:
            return "Errors: " + "; ".join(errors)
        return "Persona saved."

    persona_save_btn.click(
        _save_persona,
        inputs=[
            persona_full_name, persona_preferred, persona_birthdate,
            persona_location, persona_lat, persona_lon, persona_tz,
            persona_employer, persona_title,
            persona_health, persona_interests, persona_values,
            persona_bio, family_state,
        ],
        outputs=[persona_status],
        api_visibility="private",
    )

    # --- Backup ---
    def _handle_backup():
        result = backup_database()
        return (
            f"Backup created: {result}",
            _backups_to_df(),
            gr.Dropdown(choices=_backup_names()),
        )

    backup_btn.click(
        _handle_backup,
        outputs=[db_status_msg, backups_table, restore_dropdown],
        api_visibility="private",
    )

    # --- Restore ---
    def _handle_restore(backup_name):
        if not backup_name:
            return "Select a backup to restore", _backups_to_df()
        result = restore_database(backup_name)
        return result, _backups_to_df()

    restore_btn.click(
        _handle_restore,
        inputs=[restore_dropdown],
        outputs=[db_status_msg, backups_table],
        api_visibility="private",
    )

    # --- Reset ---
    def _handle_reset():
        result = reset_database()
        return result, _backups_to_df(), gr.Dropdown(choices=_backup_names())

    reset_btn.click(
        _handle_reset,
        outputs=[reset_status, backups_table, restore_dropdown],
        api_visibility="private",
    )

    # --- Export ---
    def _handle_export():
        return export_platform_data()

    export_btn.click(
        _handle_export, outputs=[export_status], api_visibility="private"
    )

    # --- Import ---
    def _handle_import(path):
        if not path.strip():
            return "Provide an export file path."
        return import_platform_data(path.strip())

    import_btn.click(
        _handle_import, inputs=[import_path],
        outputs=[import_status], api_visibility="private",
    )

    # --- Logs ---
    def _refresh_logs(level, module):
        from services.log_config import get_logs
        rows = get_logs(level=level, module=module, limit=200)
        if not rows:
            return pd.DataFrame(
                columns=["timestamp", "level", "module", "function", "message"]
            )
        return pd.DataFrame([{
            "timestamp": r.get("timestamp", ""),
            "level": r.get("level", ""),
            "module": r.get("module", ""),
            "function": r.get("function", ""),
            "message": r.get("message", "")[:200],
        } for r in rows])

    log_refresh_btn.click(
        _refresh_logs,
        inputs=[log_level_filter, log_module_filter],
        outputs=[log_table],
        api_visibility="private",
    )

    # --- Schema ---
    schema_refresh_btn.click(
        get_schema_info, outputs=[schema_display], api_visibility="private"
    )

    # === WIRE CHAT SIDEBAR ===
    wire_chat_sidebar(chat_input, chatbot, chat_history, sidebar_conv_id)


# ---------------------------------------------------------------------------
# Standalone testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    from db.operations import init_database
    from services.settings import init_settings
    init_database()
    init_settings()

    with gr.Blocks(title="JANATPMP — Admin") as demo:
        build_admin_page()

    demo.launch(server_name="0.0.0.0", server_port=7863, show_error=True)
