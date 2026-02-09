"""Database tab -- Stats, schema, backup, restore, reset."""
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
    """Build the Database tab. Returns dict of components."""
    with gr.Tab("Database"):
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
        'stats': stats_display,
        'schema': schema_display,
        'backups_table': backups_table,
        'restore_dropdown': restore_dropdown
    }
