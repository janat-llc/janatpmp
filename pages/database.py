"""Database page — Schema viewer, backups, and lifecycle management."""
import gradio as gr
from tabs.tab_database import build_database_tab

with gr.Blocks() as demo:
    gr.Markdown("## Database Management")
    build_database_tab()

if __name__ == "__main__":
    demo.launch(theme=gr.themes.Soft())
