

import gradio as gr

BG = "#0D0F0C"        
BG_RAISED = "#161915"    
TEXT = "#E8E6DE"        
MUTED = "#8A8F84"
AMBER = "#E8A33D"        
AMBER_DIM = "#8C6423"
FLAG_RED = "#E15252"
RULE = "#2A2E28"


theme = gr.themes.Base(
    font=[gr.themes.GoogleFont("IBM Plex Mono"), "Consolas", "monospace"],
    font_mono=[gr.themes.GoogleFont("IBM Plex Mono"), "Consolas", "monospace"],
).set(
    body_background_fill=BG,
    body_background_fill_dark=BG,
    body_text_color=TEXT,
    body_text_color_dark=TEXT,
    background_fill_primary=BG_RAISED,
    background_fill_primary_dark=BG_RAISED,
    background_fill_secondary=BG,
    background_fill_secondary_dark=BG,
    border_color_primary=RULE,
    border_color_primary_dark=RULE,
    block_background_fill=BG_RAISED,
    block_background_fill_dark=BG_RAISED,
    block_border_color=RULE,
    block_border_color_dark=RULE,
    block_label_text_color=MUTED,
    block_label_text_color_dark=MUTED,
    block_title_text_color=AMBER,
    block_title_text_color_dark=AMBER,
    button_primary_background_fill=AMBER,
    button_primary_background_fill_dark=AMBER,
    button_primary_background_fill_hover=TEXT,
    button_primary_background_fill_hover_dark=TEXT,
    button_primary_text_color=BG,
    button_primary_text_color_dark=BG,
    button_secondary_background_fill=BG_RAISED,
    button_secondary_background_fill_dark=BG_RAISED,
    button_secondary_border_color=RULE,
    button_secondary_border_color_dark=RULE,
    button_secondary_text_color=TEXT,
    button_secondary_text_color_dark=TEXT,
    input_background_fill=BG,
    input_background_fill_dark=BG,
    input_border_color=RULE,
    input_border_color_dark=RULE,
    body_text_size="15px",
)

CUSTOM_CSS = f"""
html, body, .dark, .gradio-container {{
    background-color: {BG} !important;
    color: {TEXT} !important;
}}

.gradio-container {{
    max-width: 960px !important;
    margin: 0 auto !important;
}}

.dark .block, .dark .form, .dark .panel {{
    background-color: {BG_RAISED} !important;
    border-color: {RULE} !important;
}}

* {{
    font-family: 'IBM Plex Mono', monospace !important;
}}

/* Masthead — amber ticker rule instead of a hero banner */
#ledger-masthead {{
    border-bottom: 1px solid {AMBER_DIM};
    padding-bottom: 14px;
    margin-bottom: 6px;
}}
#ledger-masthead h1 {{
    font-size: 26px;
    font-weight: 700;
    letter-spacing: 0.08em;
    color: {AMBER};
    margin: 0 0 4px 0;
}}
#ledger-cursor {{
    display: inline-block;
    animation: ledger-blink 1.1s steps(1) infinite;
}}
@keyframes ledger-blink {{
    0%, 49% {{ opacity: 1; }}
    50%, 100% {{ opacity: 0; }}
}}
@media (prefers-reduced-motion: reduce) {{
    #ledger-cursor {{ animation: none; opacity: 1; }}
}}
#ledger-masthead p {{
    font-size: 12px;
    letter-spacing: 0.04em;
    color: {MUTED};
    margin: 0;
}}

/* Tabs styled like terminal channel switches */
.tab-nav button {{
    font-size: 13px !important;
    border-radius: 0 !important;
    color: {MUTED} !important;
}}
.tab-nav .selected {{
    color: {AMBER} !important;
    border-color: {AMBER} !important;
}}

/* Evidence block — a data-feed line, amber left rule */
.evidence-line {{
    font-size: 13px;
    color: {MUTED};
    border-left: 2px solid {AMBER};
    padding: 2px 0 2px 10px;
    margin: 2px 0;
}}

/* Figures render in amber, the terminal's signal color */
.ledger-value {{
    font-variant-numeric: tabular-nums;
    font-weight: 700;
    color: {AMBER};
}}

.ledger-flag {{
    color: {FLAG_RED};
    font-size: 13px;
    font-weight: 700;
}}

/* Dataframes: hairline rules, no card shadow, no rounded corners */
.gr-dataframe, table {{
    border-radius: 0 !important;
    box-shadow: none !important;
    border-color: {RULE} !important;
}}
"""