"""Admin tab — database lifecycle, content ingestion, vector store, logs."""
import logging
import gradio as gr
import pandas as pd
from db.operations import (
    backup_database, restore_database, reset_database, list_backups
)

logger = logging.getLogger(__name__)




def _backups_to_df() -> pd.DataFrame:
    """Get backups as display DataFrame.

    Returns:
        DataFrame with columns: Name, Size (KB), Stores, Created.
    """
    backups = list_backups()
    if not backups:
        return pd.DataFrame(columns=["Name", "Size (KB)", "Stores", "Created"])
    return pd.DataFrame([{
        "Name": b['name'],
        "Size (KB)": round(b['size'] / 1024, 1),
        "Stores": b.get('stores', 'SQLite only'),
        "Created": b['created'][:19],
    } for b in backups])


def _backup_names() -> list:
    """Get list of backup filenames for dropdown.

    Returns:
        List of backup filename strings.
    """
    return [b['name'] for b in list_backups()]


def _handle_backup():
    """Create a database backup.

    Returns:
        Tuple of (status_message, backups_df, dropdown_update).
    """
    result = backup_database()
    return (
        f"Backup created: {result}",
        _backups_to_df(),
        gr.Dropdown(choices=_backup_names())
    )


def _handle_restore(backup_name):
    """Restore database from a named backup file.

    Args:
        backup_name: Filename of the backup to restore.

    Returns:
        Tuple of (status_message, backups_df).
    """
    if not backup_name:
        return "Select a backup to restore", _backups_to_df()
    result = restore_database(backup_name)
    return result, _backups_to_df()


def _handle_reset():
    """Reset database to empty state (auto-creates backup first).

    Returns:
        Tuple of (status_message, backups_df, dropdown_update).
    """
    result = reset_database()
    return (
        result,
        _backups_to_df(),
        gr.Dropdown(choices=_backup_names()),
    )


def build_database_tab(conversations_state=None, admin_refresh=None):
    """Build the Admin tab with DB lifecycle, content ingestion, vector store, logs.

    All chat and model settings are managed in Chat -> Settings tab.

    Args:
        conversations_state: Optional gr.State holding conversation list.
            If provided, reset clears it to avoid stale sidebar data.
        admin_refresh: Optional gr.State(int) bumped after DB-changing operations
            to trigger sidebar stats re-render.

    Returns:
        Dict of key components for external reference.
    """
    with gr.Tab("Admin") as admin_tab:
        # Database lifecycle
        with gr.Accordion("Database", open=False):
            gr.Markdown("### Backup & Restore")
            with gr.Row():
                backup_btn = gr.Button("Backup Now", variant="primary")
                db_status_msg = gr.Textbox(label="Status", interactive=False, scale=2)

            backups_table = gr.DataFrame(
                value=_backups_to_df(),
                interactive=False, label="Available Backups"
            )

            with gr.Row():
                restore_dropdown = gr.Dropdown(
                    label="Select Backup", choices=_backup_names(),
                    allow_custom_value=True, scale=2,
                )
                restore_btn = gr.Button("Restore Selected Backup", scale=1)

            gr.Markdown("---")
            with gr.Row():
                with gr.Column(scale=1):
                    gr.Markdown("### Portable Export")
                    gr.Markdown(
                        "Export project data (domains, items, tasks, relationships) to a "
                        "versioned JSON file. After a platform reset, import via Content Ingestion."
                    )
                    export_btn = gr.Button("Export Project Data", variant="primary")
                    export_status_msg = gr.Textbox(label="Export Status", interactive=False)

                    def _handle_export():
                        from db.operations import export_platform_data
                        return export_platform_data()

                    export_btn.click(
                        _handle_export,
                        outputs=[export_status_msg],
                        api_visibility="private",
                    )

                with gr.Column(scale=1):
                    gr.Markdown("### Reset Database")
                    gr.Markdown(
                        "Full platform reset — wipes **SQLite**, **Qdrant** vectors, and **Neo4j** graph. "
                        "SQLite backup created automatically. Re-run ingestion + embedding after reset."
                    )
                    reset_btn = gr.Button("Reset Database", variant="stop")
                    reset_status_msg = gr.Textbox(label="Reset Status", interactive=False)

        # Content Ingestion
        with gr.Accordion("Content Ingestion", open=False):
            gr.Markdown("Import conversations and documents from external sources.")
            from services.settings import get_setting as _get_ingestion

            gr.Markdown("#### Ingestion Directories")
            ingestion_claude_dir = gr.Textbox(
                label="Claude Export Directory",
                value=_get_ingestion("claude_export_json_dir"),
                placeholder="/app/imports/claude",
                interactive=True,
            )
            ingestion_google_dir = gr.Textbox(
                label="Google AI Studio Directory",
                value=_get_ingestion("ingestion_google_ai_dir"),
                placeholder="/app/imports/google_ai",
                interactive=True,
            )
            ingestion_markdown_dir = gr.Textbox(
                label="Markdown / Text Directory",
                value=_get_ingestion("ingestion_markdown_dir"),
                placeholder="/app/imports/markdown",
                interactive=True,
            )
            with gr.Row():
                save_ingestion_btn = gr.Button("Save Paths", variant="primary")
                ingestion_save_status = gr.Textbox(show_label=False, interactive=False, scale=2)

            def _save_ingestion_paths(claude_dir, google_dir, md_dir):
                from services.settings import set_setting
                set_setting("claude_export_json_dir", claude_dir.strip())
                set_setting("ingestion_google_ai_dir", google_dir.strip())
                set_setting("ingestion_markdown_dir", md_dir.strip())
                return "Ingestion paths saved."

            save_ingestion_btn.click(
                _save_ingestion_paths,
                inputs=[ingestion_claude_dir, ingestion_google_dir, ingestion_markdown_dir],
                outputs=[ingestion_save_status],
                api_visibility="private",
            )

            gr.Markdown("---")
            gr.Markdown("#### Platform Data Import")
            gr.Markdown(
                "Re-import items, tasks, and relationships from a portable export. "
                "After import, run **Embed All Items** and **Embed All Tasks** in Vector Store."
            )
            import_path_input = gr.Textbox(
                label="Export File Path",
                placeholder="/app/db/exports/platform_export_20260222_153000.json",
                interactive=True,
            )
            with gr.Row():
                import_btn = gr.Button("Import Platform Data", variant="primary")
                import_status = gr.Textbox(show_label=False, interactive=False, scale=2)

            def _handle_import(path):
                if not path.strip():
                    return "Provide an export file path."
                from db.operations import import_platform_data
                return import_platform_data(path.strip())

            import_btn.click(
                _handle_import,
                inputs=[import_path_input],
                outputs=[import_status],
                api_visibility="private",
            )

            gr.Markdown("---")
            gr.Markdown("### Run Ingestion")
            gr.Markdown(
                "Claude import scans for `conversations*.json` files in the directory. "
                "Google AI imports chunkedPrompt JSON. Markdown imports .md and .txt files."
            )
            with gr.Row():
                ingest_claude_btn = gr.Button("Ingest Claude", variant="primary")
                ingest_google_btn = gr.Button("Ingest Google AI", variant="primary")
                ingest_markdown_btn = gr.Button("Ingest Markdown/Text", variant="primary")
            ingestion_result = gr.JSON(label="Ingestion Results", value={})

            def _ingest_claude(directory):
                if not directory.strip():
                    return {"error": "Claude export directory is empty. Set it above and save."}
                try:
                    from services.claude_import import import_conversations_directory
                    return import_conversations_directory(directory.strip())
                except Exception as e:
                    return {"error": str(e)}

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

            ingest_claude_click = ingest_claude_btn.click(
                _ingest_claude, inputs=[ingestion_claude_dir],
                outputs=[ingestion_result], api_visibility="private",
            )
            ingest_google_click = ingest_google_btn.click(
                _ingest_google, inputs=[ingestion_google_dir],
                outputs=[ingestion_result], api_visibility="private",
            )
            ingest_markdown_click = ingest_markdown_btn.click(
                _ingest_markdown, inputs=[ingestion_markdown_dir],
                outputs=[ingestion_result], api_visibility="private",
            )

        # Auto-Ingestion (R17)
        with gr.Accordion("Auto-Ingestion", open=False):
            gr.Markdown(
                "Scan configured directories for new files. Runs automatically "
                "at startup and during Slumber idle cycles."
            )
            scan_btn = gr.Button("Scan & Ingest Now", variant="primary")
            scan_result = gr.JSON(label="Scan Result", value={})

            gr.Markdown("### File Registry")

            def _load_registry_stats():
                try:
                    from db.file_registry_ops import get_file_registry_stats
                    return get_file_registry_stats()
                except Exception:
                    return {}

            def _load_recent_files():
                try:
                    from db.file_registry_ops import list_registered_files
                    import pandas as pd
                    files = list_registered_files(limit=20)
                    if not files:
                        return pd.DataFrame()
                    return pd.DataFrame([{
                        "filename": f["filename"],
                        "type": f["ingestion_type"],
                        "status": f["status"],
                        "entities": f["entity_count"],
                        "ingested": f["ingested_at"],
                    } for f in files])
                except Exception:
                    import pandas as pd
                    return pd.DataFrame()

            registry_stats = gr.JSON(label="Registry Stats", value=_load_registry_stats())
            registry_table = gr.DataFrame(
                label="Recent Files", value=_load_recent_files(), interactive=False,
            )

            def _run_scan():
                try:
                    from services.auto_ingest import scan_and_ingest
                    return scan_and_ingest(auto_embed=True, source="manual")
                except Exception as e:
                    return {"error": str(e)}

            def _refresh_registry():
                return _load_registry_stats(), _load_recent_files()

            scan_click = scan_btn.click(
                _run_scan, outputs=[scan_result], api_visibility="private",
            )
            scan_click.then(
                _refresh_registry, outputs=[registry_stats, registry_table],
                api_visibility="private",
            )

        # Vector Store (Qdrant)
        with gr.Accordion("Vector Store (Qdrant)", open=False):
            gr.Markdown("Embed entities into Qdrant for semantic search and RAG.")
            gr.Markdown(
                "**R16 Chunking:** Run chunking first to split long messages/documents "
                "into focused chunks, then embed. Short texts stay as single vectors."
            )
            with gr.Row():
                chunk_msgs_btn = gr.Button("Chunk All Messages", variant="secondary")
                chunk_docs_btn = gr.Button("Chunk All Documents", variant="secondary")
            with gr.Row():
                embed_docs_btn = gr.Button("Embed All Documents", variant="primary")
                embed_msgs_btn = gr.Button("Embed All Messages", variant="primary")
            with gr.Row():
                embed_items_btn = gr.Button("Embed All Items", variant="primary")
                embed_tasks_btn = gr.Button("Embed All Tasks", variant="primary")
            embed_status = gr.JSON(label="Embedding / Chunking Status", value={})

            def _chunk_msgs():
                try:
                    from services.bulk_embed import chunk_all_messages
                    return chunk_all_messages()
                except Exception as e:
                    return {"error": str(e)}

            def _chunk_docs():
                try:
                    from services.bulk_embed import chunk_all_documents
                    return chunk_all_documents()
                except Exception as e:
                    return {"error": str(e)}

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

            def _embed_items():
                try:
                    from services.bulk_embed import embed_all_items
                    return embed_all_items()
                except Exception as e:
                    return {"error": str(e)}

            def _embed_tasks():
                try:
                    from services.bulk_embed import embed_all_tasks
                    return embed_all_tasks()
                except Exception as e:
                    return {"error": str(e)}

            chunk_msgs_btn.click(_chunk_msgs, outputs=[embed_status], api_visibility="private")
            chunk_docs_btn.click(_chunk_docs, outputs=[embed_status], api_visibility="private")
            embed_docs_btn.click(_embed_docs, outputs=[embed_status], api_visibility="private")
            embed_msgs_btn.click(_embed_msgs, outputs=[embed_status], api_visibility="private")
            embed_items_btn.click(_embed_items, outputs=[embed_status], api_visibility="private")
            embed_tasks_btn.click(_embed_tasks, outputs=[embed_status], api_visibility="private")

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

        # Wiring — outputs stay within this tab
        backup_click = backup_btn.click(
            _handle_backup,
            inputs=[],
            outputs=[db_status_msg, backups_table, restore_dropdown],
            api_visibility="private"
        )
        restore_click = restore_btn.click(
            _handle_restore,
            inputs=[restore_dropdown],
            outputs=[db_status_msg, backups_table],
            api_visibility="private"
        )
        reset_click = reset_btn.click(
            _handle_reset,
            inputs=[],
            outputs=[reset_status_msg, backups_table, restore_dropdown],
            api_visibility="private"
        )
        if conversations_state is not None:
            reset_click.then(
                lambda: [],
                outputs=[conversations_state],
                api_visibility="private",
            )

        # Bump admin_refresh after DB-changing operations → sidebar stats re-render
        if admin_refresh is not None:
            _bump = lambda n: (n or 0) + 1
            for click_event in [
                backup_click, restore_click, reset_click,
                ingest_claude_click, ingest_google_click, ingest_markdown_click,
                scan_click,
            ]:
                click_event.then(
                    _bump, inputs=[admin_refresh], outputs=[admin_refresh],
                    api_visibility="private",
                )

    return {
        'tab': admin_tab,
        'backups_table': backups_table,
        'restore_dropdown': restore_dropdown,
    }
