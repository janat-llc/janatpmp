"""Janat brand theme for Gradio — black backgrounds, cyan accents, purple depth."""

from gradio.themes.base import Base
from gradio.themes.utils import colors, fonts, sizes


class JanatTheme(Base):
    """Custom Gradio theme implementing the Janat, LLC brand guide.

    Color palette: Pure Black backgrounds, Mat Cyan (#00FFFF) primary accent,
    Janus Purple (#330033) secondary, white/off-white text.
    Typography: Rajdhani (body), Orbitron (display, via CSS only).
    """

    def __init__(self):
        janat_cyan = colors.Color(
            name="janat_cyan",
            c50="#e0ffff", c100="#b3ffff", c200="#80ffff", c300="#4dffff",
            c400="#1affff", c500="#00ffff", c600="#00cccc", c700="#009999",
            c800="#006666", c900="#003333", c950="#001a1a",
        )
        janat_purple = colors.Color(
            name="janat_purple",
            c50="#f2e6f2", c100="#d9b3d9", c200="#bf80bf", c300="#a64da6",
            c400="#8c1a8c", c500="#730073", c600="#590059", c700="#400040",
            c800="#330033", c900="#1a001a", c950="#0d000d",
        )
        janat_neutral = colors.Color(
            name="janat_neutral",
            c50="#f5f5f5", c100="#e0e0e0", c200="#b3b3b3", c300="#808080",
            c400="#4d4d4d", c500="#333333", c600="#262626", c700="#1a1a1a",
            c800="#111111", c900="#0a0a0a", c950="#050505",
        )

        super().__init__(
            primary_hue=janat_cyan,
            secondary_hue=janat_purple,
            neutral_hue=janat_neutral,
            spacing_size=sizes.spacing_md,
            radius_size=sizes.radius_sm,
            text_size=sizes.text_md,
            font=[
                fonts.GoogleFont("Rajdhani"),
                "ui-sans-serif",
                "sans-serif",
            ],
            font_mono=[
                fonts.GoogleFont("IBM Plex Mono"),
                "ui-monospace",
                "monospace",
            ],
        )

        # Dark mode overrides — Janat is dark-first
        super().set(
            # Backgrounds
            body_background_fill="#111111",
            body_background_fill_dark="#000000",
            block_background_fill="#1a1a1a",
            block_background_fill_dark="#0a0a0a",
            block_border_color="#262626",
            block_border_color_dark="#1a1a1a",
            input_background_fill="#1a1a1a",
            input_background_fill_dark="#111111",
            # Text
            body_text_color="#333333",
            body_text_color_dark="#e0e0e0",
            block_label_text_color="*neutral_300",
            block_label_text_color_dark="*neutral_300",
            block_title_text_color="*neutral_200",
            block_title_text_color_dark="*neutral_200",
            input_placeholder_color="*neutral_500",
            input_placeholder_color_dark="*neutral_500",
            # Primary buttons — cyan on dark
            button_primary_background_fill="*primary_500",
            button_primary_background_fill_dark="*primary_500",
            button_primary_background_fill_hover="*primary_400",
            button_primary_background_fill_hover_dark="*primary_400",
            button_primary_text_color="#000000",
            button_primary_text_color_dark="#000000",
            button_primary_border_color="*primary_600",
            button_primary_border_color_dark="*primary_600",
            # Secondary buttons — purple accent
            button_secondary_background_fill="*neutral_700",
            button_secondary_background_fill_dark="*neutral_800",
            button_secondary_text_color="*neutral_100",
            button_secondary_text_color_dark="*neutral_200",
            # Accents
            loader_color="#00FFFF",
            slider_color="*primary_500",
            slider_color_dark="*primary_500",
            # Borders and shadows
            block_border_width="1px",
            block_shadow="none",
            block_shadow_dark="none",
            # Links
            link_text_color="*primary_400",
            link_text_color_dark="*primary_400",
            link_text_color_hover="*primary_300",
            link_text_color_hover_dark="*primary_300",
        )


# Custom CSS — co-located with theme for single-source brand styling
JANAT_CSS = """
    /* === Brand colors === */
    .gradio-container { background: #000000 !important; }
    .dark .gradio-container { background: #000000 !important; }

    /* Tab styling */
    .tab-nav button {
        font-family: 'Rajdhani', sans-serif !important;
        letter-spacing: 0.05em !important;
        font-weight: 600 !important;
    }
    .tab-nav button.selected {
        color: #00FFFF !important;
        border-color: #00FFFF !important;
    }

    /* Sidebar backgrounds */
    .sidebar { background: #0a0a0a !important; border-color: #1a1a1a !important; }

    /* Right panel header — right-justified to avoid toggle overlap */
    .right-panel-header { text-align: right !important; }

    /* === Right sidebar — strip nested container chrome, fill height === */
    .sidebar.right .sidebar-content {
        height: 100% !important;
        display: flex !important;
        flex-direction: column !important;
        padding: 2px !important;
        overflow: hidden !important;
        box-sizing: border-box !important;
    }
    /* Flatten ALL nested wrappers Gradio generates inside sidebar */
    .sidebar.right .sidebar-content .column,
    .sidebar.right .sidebar-content .form,
    .sidebar.right .sidebar-content .block,
    .sidebar.right .sidebar-content .wrap,
    .sidebar.right .sidebar-content .wrapper {
        padding: 0 !important;
        margin: 0 !important;
        border: none !important;
        box-shadow: none !important;
        background: transparent !important;
        overflow: hidden !important;
    }
    .sidebar.right .sidebar-content > .column {
        flex: 1 !important;
        display: flex !important;
        flex-direction: column !important;
        min-height: 0 !important;
    }
    .sidebar.right .chatbot {
        flex: 1 1 0 !important;
        min-height: 0 !important;
        overflow-y: auto !important;
        overflow-x: hidden !important;
    }

    /* Force sidebar chatbot and ALL children to respect container width */
    #sidebar-chatbot,
    #sidebar-chatbot * {
        max-width: 100% !important;
        min-width: 0 !important;
        box-sizing: border-box !important;
    }

    /* Right sidebar chat density — strip chatbot internal padding */
    #sidebar-chatbot .chatbot-chat-wrap,
    #sidebar-chatbot .messages-wrap,
    #sidebar-chatbot .scroll-container,
    #sidebar-chatbot > div {
        padding: 2px !important;
    }
    .sidebar.right .message-row { max-width: 100% !important; padding: 0 !important; margin: 0 !important; }
    .sidebar.right .message { padding: 4px 6px !important; max-width: 100% !important; word-break: break-word !important; }
    .sidebar.right .bubble-wrap { padding: 0 !important; }

    /* Push fixed sidebars below the navbar (Gradio doesn't do this automatically) */
    .sidebar { top: 48px !important; height: calc(100vh - 48px) !important; }

    /* === Branded navbar — restyle Gradio's built-in nav === */
    .nav-holder {
        background: transparent !important;
        border-bottom: 1px solid #1a1a1a !important;
        padding: 0 20px !important;
        display: flex !important;
        align-items: center !important;
        height: 48px !important;
        box-sizing: border-box !important;
    }
    /* JANATPMP title — injected via CSS pseudo-element */
    .nav-holder::before {
        content: "JANATPMP";
        font-family: 'Orbitron', sans-serif;
        font-size: 1.4rem;
        font-weight: 700;
        color: #00FFFF;
        letter-spacing: 0.15em;
        margin-right: 24px;
        flex-shrink: 0;
    }
    /* "Powered by" + logo on the right */
    .nav-holder::after {
        content: "Powered by";
        font-family: 'Rajdhani', sans-serif;
        font-size: 0.75rem;
        color: #808080;
        letter-spacing: 0.05em;
        flex-shrink: 0;
        margin-left: auto;
        padding-right: 36px;
        background: url("/gradio_api/file=assets/janat_logo_bold_transparent.png") right center / auto 28px no-repeat;
        line-height: 28px;
    }
    /* Nav links — left-aligned, brand-styled */
    .nav-holder nav {
        justify-content: flex-start !important;
        padding: 0 !important;
        margin: 0 !important;
        flex: 0 0 auto !important;
        flex-wrap: nowrap !important;
        gap: 16px !important;
    }
    .nav-holder nav a {
        font-family: 'Rajdhani', sans-serif !important;
        font-size: 0.95rem !important;
        font-weight: 600 !important;
        color: #808080 !important;
        letter-spacing: 0.05em !important;
        border: none !important;
        background: transparent !important;
        padding: 4px 0 !important;
    }
    .nav-holder nav a:hover { color: #00FFFF !important; }
    .nav-holder nav a.active {
        color: #00FFFF !important;
        background: transparent !important;
        border: none !important;
    }

    /* Hide Gradio footer */
    footer { display: none !important; }

    /* === Chat page — chatbot fills viewport === */
    #chat-page-chatbot {
        height: calc(100vh - 260px) !important;
        min-height: 300px !important;
        overflow-y: auto !important;
    }
"""
