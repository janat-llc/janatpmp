"""Documents tab -- Browse, filter, and create documents."""
import gradio as gr
import pandas as pd
from db.operations import list_documents, create_document


def _format_display(value: str) -> str:
    """Convert enum values like 'agent_output' to 'Agent Output'."""
    return value.replace("_", " ").title() if value else ""


def _docs_to_df(doc_type="", source="") -> pd.DataFrame:
    """Fetch documents and return as display DataFrame."""
    docs = list_documents(doc_type=doc_type, source=source, limit=100)
    if not docs:
        return pd.DataFrame(columns=["ID", "Title", "Type", "Source", "Created"])
    return pd.DataFrame([{
        "ID": doc['id'][:8],
        "Title": doc['title'],
        "Type": _format_display(doc['doc_type']),
        "Source": _format_display(doc['source']),
        "Created": doc.get('created_at', '')[:16]
    } for doc in docs])


def _handle_create(doc_type, source, title, content):
    """Create document, return status message + refreshed table + cleared fields."""
    if not title.strip():
        return "Title is required", _docs_to_df(), gr.update(), gr.update()
    doc_id = create_document(
        doc_type=doc_type, source=source,
        title=title.strip(),
        content=content.strip() if content else ""
    )
    return (
        f"Created: {doc_id[:8]}",
        _docs_to_df(),
        gr.update(value=""),  # clear title
        gr.update(value=""),  # clear content
    )


def build_documents_tab():
    """Build the Documents tab. Returns docs_table component."""
    with gr.Tab("Documents"):
        with gr.Row():
            # Left: Table with filters
            with gr.Column(scale=2):
                gr.Markdown("### Documents")
                with gr.Row():
                    doc_type_filter = gr.Dropdown(
                        label="Type",
                        choices=["", "conversation", "file", "artifact", "research",
                                 "agent_output", "session_notes", "code"],
                        value=""
                    )
                    source_filter = gr.Dropdown(
                        label="Source",
                        choices=["", "claude_exporter", "upload", "agent", "generated", "manual"],
                        value=""
                    )
                    refresh_btn = gr.Button("Refresh", variant="secondary", size="sm")

                docs_table = gr.DataFrame(
                    value=_docs_to_df(),
                    interactive=False
                )

            # Right: Create form
            with gr.Column(scale=1):
                gr.Markdown("### Create Document")
                doc_type = gr.Dropdown(
                    label="Type",
                    choices=["conversation", "file", "artifact", "research",
                             "agent_output", "session_notes", "code"],
                    value="session_notes"
                )
                source = gr.Dropdown(
                    label="Source",
                    choices=["manual", "claude_exporter", "upload", "agent", "generated"],
                    value="manual"
                )
                title = gr.Textbox(label="Title", placeholder="Document title...")
                content = gr.Textbox(label="Content", lines=6, placeholder="Document content...")
                create_btn = gr.Button("Create Document", variant="primary")
                status_msg = gr.Textbox(label="Status", interactive=False)

        # Wiring -- auto-filter on dropdown change, Refresh for MCP changes
        filter_inputs = [doc_type_filter, source_filter]
        doc_type_filter.change(_docs_to_df, inputs=filter_inputs, outputs=[docs_table], api_visibility="private")
        source_filter.change(_docs_to_df, inputs=filter_inputs, outputs=[docs_table], api_visibility="private")
        refresh_btn.click(_docs_to_df, inputs=filter_inputs, outputs=[docs_table], api_visibility="private")
        create_btn.click(
            _handle_create,
            inputs=[doc_type, source, title, content],
            outputs=[status_msg, docs_table, title, content],
            api_visibility="private"
        )

    return docs_table
