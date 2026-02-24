"""Reusable Janus quick-chat right sidebar — shared across all sovereign pages.

Each page calls build_chat_sidebar() before its center content to create
the right sidebar, then wire_chat_sidebar() after all center content
is declared to connect the submit event.
"""

import gradio as gr


def build_chat_sidebar():
    """Build right sidebar with Janus quick-chat.

    Must be called inside a gr.Blocks context BEFORE center content.

    Returns:
        Tuple of (chatbot, chat_input, chat_history, sidebar_conv_id)
        for wiring via wire_chat_sidebar().
    """
    from shared.data_helpers import _load_chat_session
    from db.chat_operations import get_or_create_janus_conversation

    chat_history = gr.State(lambda: _load_chat_session()["api_history"])
    sidebar_conv_id = gr.State(get_or_create_janus_conversation)

    with gr.Sidebar(position="right"):
        gr.Markdown("### Janat", elem_classes=["right-panel-header"])
        chatbot = gr.Chatbot(
            value=lambda: _load_chat_session()["display_history"],
            show_label=False,
            buttons=["copy"],
            scale=1, min_height=300,
            elem_id="sidebar-chatbot",
        )
        chat_input = gr.Textbox(
            placeholder="What should We do?",
            show_label=False, interactive=True, max_lines=5, lines=3,
        )

    return chatbot, chat_input, chat_history, sidebar_conv_id


def wire_chat_sidebar(chat_input, chatbot, chat_history, sidebar_conv_id):
    """Wire chat sidebar submit event. Call AFTER all center content is declared."""
    from tabs.tab_chat import _handle_chat

    chat_input.submit(
        _handle_chat,
        inputs=[chat_input, chat_history, sidebar_conv_id],
        outputs=[chatbot, chat_history, chat_input, sidebar_conv_id],
        api_visibility="private",
    )
