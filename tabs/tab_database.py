"""Admin tab -- System prompt editor, stats, schema, backup, restore, reset."""
import json
import gradio as gr
import pandas as pd
from db.operations import (
    get_stats, get_schema_info,
    backup_database, restore_database, reset_database, list_backups
)


def _load_stats() -> dict:
    """Get database stats dict for gr.JSON display."""
    return get_stats()


def _load_schema() -> str:
    """Get schema info as formatted JSON string."""
    try:
        return json.dumps(get_schema_info(), indent=2)
    except Exception:
        return "{}"


def _load_system_prompt() -> str:
    """Load custom system prompt from settings DB."""
    from services.settings import get_setting
    return get_setting("chat_system_prompt")


def _backups_to_df() -> pd.DataFrame:
    """Get backups as display DataFrame."""
    backups = list_backups()
    if not backups:
        return pd.DataFrame(columns=["Name", "Size (KB)", "Created"])
    return pd.DataFrame([{
        "Name": b['name'],
        "Size (KB)": round(b['size'] / 1024, 1),
        "Created": b['created'][:19]
    } for b in backups])


def _backup_names() -> list:
    """Get list of backup filenames for dropdown."""
    return [b['name'] for b in list_backups()]


def _handle_backup():
    """Create backup, return status + refreshed backup list."""
    result = backup_database()
    return (
        f"Backup created: {result}",
        _backups_to_df(),
        gr.Dropdown(choices=_backup_names())
    )


def _handle_restore(backup_name):
    """Restore from backup, return status + refreshed displays."""
    if not backup_name:
        return "Select a backup to restore", _load_stats(), _load_schema(), _backups_to_df()
    result = restore_database(backup_name)
    return result, _load_stats(), _load_schema(), _backups_to_df()


def _handle_reset():
    """Reset database, return status + refreshed displays."""
    result = reset_database()
    return (
        result,
        _load_stats(),
        _load_schema(),
        _backups_to_df(),
        gr.Dropdown(choices=_backup_names())
    )


def build_database_tab():
    """Build the Admin tab. Returns dict of components."""
    with gr.Tab("Admin") as admin_tab:
        # System Prompt Editor
        with gr.Accordion("System Prompt", open=False):
            gr.Markdown("Customize the AI assistant's behavior. Leave empty for default.")
            system_prompt_editor = gr.Textbox(
                label="Custom System Prompt",
                lines=6,
                placeholder="e.g., You manage JANATPMP for The Janat Initiative. Focus on actionable responses.",
                value=_load_system_prompt(),
                interactive=True,
            )
            with gr.Row():
                save_prompt_btn = gr.Button("Save Prompt", variant="primary")
                prompt_status = gr.Textbox(show_label=False, interactive=False, scale=2)

            def _save_prompt(prompt_text):
                from services.settings import set_setting
                set_setting("chat_system_prompt", prompt_text)
                return "System prompt saved."

            save_prompt_btn.click(
                _save_prompt,
                inputs=[system_prompt_editor],
                outputs=[prompt_status],
                api_visibility="private",
            )

        # Settings section
        with gr.Accordion("Settings", open=False):
            from services.settings import get_setting as _get_setting

            gr.Markdown("#### Claude Export")
            setting_export_db = gr.Textbox(
                label="Claude Export DB Path",
                value=_get_setting("claude_export_db_path"),
                placeholder="/data/claude_export/claude_export.db",
                interactive=True,
            )
            setting_export_dir = gr.Textbox(
                label="Claude Export JSON Directory",
                value=_get_setting("claude_export_json_dir"),
                placeholder="/data/claude_export",
                interactive=True,
            )

            gr.Markdown("---")
            gr.Markdown("#### Ollama")
            gr.Markdown("Context window and model persistence settings for local inference.")
            with gr.Row():
                setting_num_ctx = gr.Number(
                    label="Context Window (num_ctx)",
                    value=int(_get_setting("ollama_num_ctx")),
                    precision=0,
                    interactive=True,
                )
                setting_keep_alive = gr.Textbox(
                    label="Keep Alive",
                    value=_get_setting("ollama_keep_alive"),
                    placeholder="5m",
                    interactive=True,
                )

            with gr.Row():
                save_settings_btn = gr.Button("Save Settings", variant="primary")
                settings_status = gr.Textbox(show_label=False, interactive=False, scale=2)

            def _save_all_settings(db_path, json_dir, num_ctx, keep_alive):
                from services.settings import set_setting
                set_setting("claude_export_db_path", db_path.strip())
                set_setting("claude_export_json_dir", json_dir.strip())
                set_setting("ollama_num_ctx", str(int(num_ctx)))
                set_setting("ollama_keep_alive", keep_alive.strip())
                return "Settings saved."

            save_settings_btn.click(
                _save_all_settings,
                inputs=[setting_export_db, setting_export_dir, setting_num_ctx, setting_keep_alive],
                outputs=[settings_status],
                api_visibility="private",
            )

        # Database section (collapsible)
        with gr.Accordion("Database", open=False):
            with gr.Row():
                # Left: Stats and Schema
                with gr.Column(scale=1):
                    with gr.Row():
                        gr.Markdown("### Database Stats")
                        refresh_stats_btn = gr.Button("Refresh", variant="secondary", size="sm")
                    stats_display = gr.JSON(value=_load_stats(), label="Stats")
                    with gr.Accordion("Schema Info", open=False):
                        schema_display = gr.Code(value=_load_schema(), label="Schema", language="json", interactive=False, max_lines=30)

                # Right: Lifecycle controls
                with gr.Column(scale=1):
                    gr.Markdown("### Backup & Restore")
                    backup_btn = gr.Button("Backup Now", variant="primary")
                    db_status_msg = gr.Textbox(label="Status", interactive=False)

                    backups_table = gr.DataFrame(
                        value=_backups_to_df(),
                        interactive=False, label="Available Backups"
                    )

                    restore_dropdown = gr.Dropdown(
                        label="Select Backup", choices=_backup_names(), allow_custom_value=True
                    )
                    restore_btn = gr.Button("Restore Selected Backup")

                    gr.Markdown("---")
                    gr.Markdown("### Reset Database")
                    gr.Markdown("Deletes all data and recreates schema. A backup is created automatically.")
                    reset_btn = gr.Button("Reset Database", variant="stop")
                    reset_status_msg = gr.Textbox(label="Reset Status", interactive=False)

        # Content Ingestion
        with gr.Accordion("Content Ingestion", open=False):
            gr.Markdown("Import conversations and documents from external sources.")
            from services.settings import get_setting as _get_ingestion
            ingestion_google_dir = gr.Textbox(
                label="Google AI Studio Directory",
                value=_get_ingestion("ingestion_google_ai_dir"),
                placeholder="/app/imports/raw_data/google_ai",
                interactive=True,
            )
            ingestion_markdown_dir = gr.Textbox(
                label="Markdown / Text Directory",
                value=_get_ingestion("ingestion_markdown_dir"),
                placeholder="/app/imports/raw_data/markdown",
                interactive=True,
            )
            ingestion_quest_dir = gr.Textbox(
                label="Quest Files Directory",
                value=_get_ingestion("ingestion_quest_dir"),
                placeholder="/app/imports/raw_data/quests",
                interactive=True,
            )
            with gr.Row():
                save_ingestion_btn = gr.Button("Save Paths", variant="primary")
                ingestion_save_status = gr.Textbox(show_label=False, interactive=False, scale=2)

            def _save_ingestion_paths(google_dir, md_dir, quest_dir):
                from services.settings import set_setting
                set_setting("ingestion_google_ai_dir", google_dir.strip())
                set_setting("ingestion_markdown_dir", md_dir.strip())
                set_setting("ingestion_quest_dir", quest_dir.strip())
                return "Ingestion paths saved."

            save_ingestion_btn.click(
                _save_ingestion_paths,
                inputs=[ingestion_google_dir, ingestion_markdown_dir, ingestion_quest_dir],
                outputs=[ingestion_save_status],
                api_visibility="private",
            )

            gr.Markdown("---")
            gr.Markdown("### Run Ingestion")
            with gr.Row():
                ingest_google_btn = gr.Button("Ingest Google AI", variant="primary")
                ingest_markdown_btn = gr.Button("Ingest Markdown/Text", variant="primary")
                ingest_quest_btn = gr.Button("Ingest Quests", variant="primary")
            ingestion_result = gr.JSON(label="Ingestion Results", value={})

            def _ingest_google(directory):
                if not directory.strip():
                    return {"error": "Google AI Studio directory path is empty. Set it above and save."}
                try:
                    from services.ingestion.orchestrator import ingest_google_ai_conversations
                    return ingest_google_ai_conversations(directory.strip())
                except Exception as e:
                    return {"error": str(e)}

            def _ingest_markdown(directory):
                if not directory.strip():
                    return {"error": "Markdown directory path is empty. Set it above and save."}
                try:
                    from services.ingestion.orchestrator import ingest_markdown_documents
                    return ingest_markdown_documents(directory.strip())
                except Exception as e:
                    return {"error": str(e)}

            def _ingest_quest(directory):
                if not directory.strip():
                    return {"error": "Quest directory path is empty. Set it above and save."}
                try:
                    from services.ingestion.orchestrator import ingest_quest_documents
                    return ingest_quest_documents(directory.strip())
                except Exception as e:
                    return {"error": str(e)}

            ingest_google_btn.click(
                _ingest_google, inputs=[ingestion_google_dir],
                outputs=[ingestion_result], api_visibility="private",
            )
            ingest_markdown_btn.click(
                _ingest_markdown, inputs=[ingestion_markdown_dir],
                outputs=[ingestion_result], api_visibility="private",
            )
            ingest_quest_btn.click(
                _ingest_quest, inputs=[ingestion_quest_dir],
                outputs=[ingestion_result], api_visibility="private",
            )

        # Vector Store (Qdrant)
        with gr.Accordion("Vector Store (Qdrant)", open=False):
            gr.Markdown("Embed documents and messages into Qdrant for semantic search and RAG.")
            with gr.Row():
                embed_docs_btn = gr.Button("Embed All Documents", variant="primary")
                embed_msgs_btn = gr.Button("Embed All Messages", variant="primary")
            embed_status = gr.JSON(label="Embedding Status", value={})

            def _embed_docs():
                try:
                    from services.bulk_embed import embed_all_documents
                    return embed_all_documents()
                except Exception as e:
                    return {"error": str(e)}

            def _embed_msgs():
                try:
                    from services.bulk_embed import embed_all_messages
                    return embed_all_messages()
                except Exception as e:
                    return {"error": str(e)}

            embed_docs_btn.click(_embed_docs, outputs=[embed_status], api_visibility="private")
            embed_msgs_btn.click(_embed_msgs, outputs=[embed_status], api_visibility="private")

        # Application Logs
        with gr.Accordion("Application Logs", open=False):
            gr.Markdown("View application log entries stored in the database.")
            with gr.Row():
                log_level_filter = gr.Dropdown(
                    label="Level",
                    choices=["", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
                    value="",
                    interactive=True,
                    scale=1,
                )
                log_module_filter = gr.Textbox(
                    label="Module Filter",
                    placeholder="e.g. chat, settings",
                    value="",
                    interactive=True,
                    scale=2,
                )
                log_refresh_btn = gr.Button("Refresh", variant="primary", scale=0)

            log_table = gr.DataFrame(
                value=pd.DataFrame(columns=["timestamp", "level", "module", "function", "message"]),
                interactive=False,
                label="Recent Logs",
                wrap=True,
            )

            def _refresh_logs(level, module):
                from services.log_config import get_logs
                rows = get_logs(level=level, module=module, limit=200)
                if not rows:
                    return pd.DataFrame(columns=["timestamp", "level", "module", "function", "message"])
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

        # Wiring -- outputs stay within this tab
        def _handle_refresh():
            return _load_stats(), _load_schema()

        refresh_stats_btn.click(_handle_refresh, inputs=[], outputs=[stats_display, schema_display], api_visibility="private")
        backup_btn.click(
            _handle_backup,
            inputs=[],
            outputs=[db_status_msg, backups_table, restore_dropdown],
            api_visibility="private"
        )
        restore_btn.click(
            _handle_restore,
            inputs=[restore_dropdown],
            outputs=[db_status_msg, stats_display, schema_display, backups_table],
            api_visibility="private"
        )
        reset_btn.click(
            _handle_reset,
            inputs=[],
            outputs=[reset_status_msg, stats_display, schema_display, backups_table, restore_dropdown],
            api_visibility="private"
        )

    return {
        'tab': admin_tab,
        'stats': stats_display,
        'schema': schema_display,
        'backups_table': backups_table,
        'restore_dropdown': restore_dropdown,
    }
