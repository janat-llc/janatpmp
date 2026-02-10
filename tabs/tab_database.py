"""Admin tab -- Model settings, stats, schema, backup, restore, reset."""
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
    """Build the Admin tab. Returns dict of components including model config."""
    with gr.Tab("Admin") as admin_tab:
        # Model Settings
        with gr.Accordion("Model Settings", open=True):
            gr.Markdown("Configure the AI model for the sidebar chat.")
            with gr.Row():
                provider_dropdown = gr.Dropdown(
                    choices=["anthropic", "gemini", "ollama"],
                    value="anthropic",
                    label="Provider",
                    interactive=True,
                )
                model_dropdown = gr.Dropdown(
                    choices=[
                        "claude-sonnet-4-20250514",
                        "claude-haiku-4-5-20251001",
                        "claude-opus-4-6",
                    ],
                    value="claude-sonnet-4-20250514",
                    label="Model",
                    allow_custom_value=True,
                    interactive=True,
                )
            api_key_input = gr.Textbox(
                label="API Key",
                type="password",
                placeholder="sk-ant-... or AIza...",
                interactive=True,
            )
            base_url_input = gr.Textbox(
                label="Base URL (Ollama only)",
                value="http://localhost:11434/v1",
                visible=False,
                interactive=True,
            )

            def _on_provider_change(provider):
                from services.chat import PROVIDER_PRESETS
                preset = PROVIDER_PRESETS.get(provider, {})
                models = preset.get("models", [])
                default = preset.get("default_model", "")
                needs_key = preset.get("needs_api_key", True)
                is_ollama = provider == "ollama"
                return (
                    gr.Dropdown(choices=models, value=default),
                    gr.Textbox(visible=needs_key),
                    gr.Textbox(visible=is_ollama),
                )

            provider_dropdown.change(
                _on_provider_change,
                inputs=[provider_dropdown],
                outputs=[model_dropdown, api_key_input, base_url_input],
                api_visibility="private",
            )

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
        'tab': admin_tab,
        'provider': provider_dropdown,
        'model': model_dropdown,
        'api_key': api_key_input,
        'base_url': base_url_input,
        'stats': stats_display,
        'schema': schema_display,
        'backups_table': backups_table,
        'restore_dropdown': restore_dropdown,
    }
