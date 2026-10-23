"""AXIOM look for the Workbench (same design system as the AXIOM request portal)."""

from __future__ import annotations

import streamlit as st

# =============================================================================
# DESIGN TOKENS
# =============================================================================

AXIOM_PURPLE = "#663BFF"
AXIOM_PURPLE_HOVER = "#5429E8"
AXIOM_PURPLE_SOFT = "#F3EFFF"

AXIOM_DARK = "#0F1115"
AXIOM_NAVY = "#182033"

ETEX_ORANGE = "#FF5A00"

TEXT = "#182033"
TEXT_STRONG = "#101828"

MUTED = "#667085"
MUTED_LIGHT = "#98A2B3"

BORDER = "#E4E7EC"
BORDER_LIGHT = "#F0F1F3"

SURFACE = "#FFFFFF"
PAGE = "#F7F8FA"

INPUT_BG = "#F1F4F7"
CONTROL_BORDER = "#CBD5DF"
CONTROL_BORDER_HOVER = "#98A5B5"
PLACEHOLDER = "#8995A5"
TEXT_DISABLED = "#526775"

STATUS = {
    "neutral": {
        "rail": "#AEB7BE",
        "fill": "#F7F8F9",
    },
    "attention": {
        "rail": "#C59A00",
        "fill": "#FFF8DD",
    },
    "complete": {
        "rail": "#2E7D32",
        "fill": "#F0F8F1",
    },
    "error": {
        "rail": "#C62828",
        "fill": "#FFF1F1",
    },
}

# =============================================================================
# MAIN THEME
# =============================================================================

def apply_theme() -> None:
    """Apply the Axiom application theme."""

    st.markdown(
        f"""
<style>

/* ================================================================
   DESIGN VARIABLES
================================================================ */

:root {{
    --axiom-purple: {AXIOM_PURPLE};
    --axiom-purple-hover: {AXIOM_PURPLE_HOVER};
    --axiom-purple-soft: {AXIOM_PURPLE_SOFT};

    --axiom-dark: {AXIOM_DARK};
    --axiom-navy: {AXIOM_NAVY};

    --etex-orange: {ETEX_ORANGE};

    --text: {TEXT};
    --text-strong: {TEXT_STRONG};

    --muted: {MUTED};
    --muted-light: {MUTED_LIGHT};

    --border: {BORDER};
    --border-light: {BORDER_LIGHT};

    --surface: {SURFACE};
    --page: {PAGE};

    --input-bg: {INPUT_BG};
    --control-border: {CONTROL_BORDER};
    --control-border-hover: {CONTROL_BORDER_HOVER};
    --placeholder: {PLACEHOLDER};
    --text-disabled: {TEXT_DISABLED};

    --radius-card: 12px;
    --radius-control: 8px;

    --shadow-card:
        0 1px 3px rgba(16, 24, 40, 0.04),
        0 1px 2px rgba(16, 24, 40, 0.03);
}}


/* ================================================================
   STREAMLIT HEADER AND SIDEBAR
================================================================ */

header[data-testid="stHeader"] {{
    display: block !important;
    visibility: visible !important;
    background: transparent !important;
    height: 2.5rem !important;
}}

[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"] {{
    visibility: visible !important;
    opacity: 1 !important;
}}

section[data-testid="stSidebar"] {{
    visibility: visible !important;
}}


/* ================================================================
   PAGE LAYOUT
================================================================ */

[data-testid="stMain"] {{
    padding-top: 0 !important;
}}

section[data-testid="stMain"]
[data-testid="stMainBlockContainer"] {{
    width: 100% !important;
    max-width: 100% !important;

    padding-top: 0.5rem !important;
    padding-right: 2.5rem !important;
    padding-bottom: 1.5rem !important;
    padding-left: 2.5rem !important;

    margin: 0 auto !important;
}}

[data-testid="column"] {{
    min-width: 0 !important;
}}


/* ================================================================
   TYPOGRAPHY
================================================================ */

[data-testid="stMain"] p {{
    color: var(--text);
}}

[data-testid="stMain"] h3 {{
    color: var(--text-strong) !important;
    font-weight: 750 !important;
}}

[data-testid="stMain"] h5 {{
    color: #344956 !important;
    font-size: 0.86rem !important;
    line-height: 1.1rem !important;
    font-weight: 700 !important;
    margin-top: 0.3rem !important;
    margin-bottom: 0.3rem !important;
}}


/* ================================================================
   HEADER BRAND
================================================================ */

.axiom-header-title {{
    color: #182033 !important;
    font-size: 1.25rem !important;
    line-height: 1.5rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.025em !important;
    white-space: nowrap;
    margin: 0 !important;
}}

.axiom-header-description {{
    color: #7B8195 !important;
    font-size: 0.78rem !important;
    line-height: 1.15rem !important;
    font-weight: 400 !important;
    white-space: nowrap;
    margin-top: 0.18rem !important;
}}

.header-brand {{
    padding: 0.05rem 0;
}}

.header-eyebrow {{
    color: var(--axiom-purple) !important;
    font-size: 0.62rem !important;
    line-height: 0.8rem !important;
    font-weight: 750 !important;
    letter-spacing: 0.11em;
    margin-bottom: 0.12rem;
}}

.header-title {{
    color: var(--text-strong) !important;
    font-size: 1.25rem !important;
    line-height: 1.45rem !important;
    font-weight: 750 !important;
    letter-spacing: -0.02em;
}}

.st-key-axiom_main_header {{
    margin-bottom: 1rem !important;
    padding-bottom: 0 !important;
}}

.st-key-axiom_main_header
div[data-testid="stVerticalBlock"] {{
    gap: 0 !important;
}}

.st-key-axiom_main_header [data-testid="stImage"] {{
    padding: 5px 8px !important;
    box-sizing: border-box !important;
    overflow: visible !important;
}}

.st-key-axiom_main_header img {{
    display: block !important;
    object-fit: contain !important;
    max-width: 100% !important;
    height: auto !important;
    border-radius: 0 !important;
    clip-path: none !important;
}}


/* ================================================================
   CURRENT CUSTOMER
================================================================ */

.header-current-customer {{
    text-align: right;
    padding: 0.05rem 0;
}}

.header-customer-label {{
    color: var(--muted-light) !important;
    font-size: 0.60rem !important;
    line-height: 0.8rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.09em;
    margin-bottom: 0.12rem;
}}

.header-customer-value {{
    color: var(--text-strong) !important;
    font-size: 0.80rem !important;
    line-height: 1.05rem !important;
    font-weight: 650 !important;
    overflow-wrap: anywhere;
}}


/* ================================================================
   WIDGET LABELS
================================================================ */

[data-testid="stMain"] .stTextInput label,
[data-testid="stMain"] .stSelectbox label,
[data-testid="stMain"] .stTextArea label,
[data-testid="stMain"] .stFileUploader label,
[data-testid="stMain"] [data-testid="stWidgetLabel"] p {{
    color: #45545F !important;
    font-size: 0.82rem !important;
    line-height: 1.1rem !important;
    font-weight: 600 !important;
}}

div[data-testid="stExpander"]
[data-testid="stWidgetLabel"] {{
    min-height: 1.5rem !important;
    display: flex !important;
    align-items: flex-end !important;
    margin-bottom: 0.2rem !important;
}}

div[data-testid="stExpander"]
[data-testid="stWidgetLabel"] p {{
    line-height: 1.15rem !important;
    margin: 0 !important;
}}


/* ================================================================
   FORM CONTROLS
   One look for every text input, textarea and selectbox.
   The widget wrapper is the bordered box and the native element
   inside it stays transparent, so every control type has exactly
   one element to style. Covers Streamlit's React Aria markup and
   the older BaseWeb markup.
   :where() zeroes specificity so the per-widget required-state
   borders from apply_required_widget_state always win.
================================================================ */

:where([data-testid="stMain"])
:where(
    [data-testid="stTextInputRootElement"],
    [data-testid="stTextAreaRootElement"],
    .react-aria-ComboBox > [role="group"],
    div[data-baseweb="select"] > div
) {{
    box-sizing: border-box !important;
    min-height: 40px !important;
    background: var(--input-bg) !important;
    border: 1px solid var(--control-border) !important;
    border-radius: var(--radius-control) !important;
    box-shadow: none !important;
}}

:where([data-testid="stMain"])
:where([data-testid="stTextAreaRootElement"]) {{
    min-height: 72px !important;
}}

/* Inner wrappers and native elements stay transparent */
:where([data-testid="stMain"])
:where(
    [data-testid="stTextInputRootElement"] div,
    [data-testid="stTextInputRootElement"] input,
    [data-testid="stTextAreaRootElement"] textarea,
    .react-aria-ComboBox input,
    div[data-baseweb="select"] > div div,
    div[data-baseweb="select"] input
) {{
    background: transparent !important;
    border: 0 !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    outline: none !important;
}}

:where([data-testid="stMain"])
:where(
    [data-testid="stTextInputRootElement"] input,
    [data-testid="stTextAreaRootElement"] textarea,
    .react-aria-ComboBox input,
    div[data-baseweb="select"] input,
    div[data-baseweb="select"] span
) {{
    color: var(--text) !important;
    -webkit-text-fill-color: var(--text) !important;
    opacity: 1 !important;
    font-weight: 500 !important;
}}

/* Same text inset for inputs and selects */
:where([data-testid="stMain"])
:where(
    [data-testid="stTextInputRootElement"] input,
    [data-testid="stTextAreaRootElement"] textarea,
    .react-aria-ComboBox input
) {{
    padding-left: 12px !important;
    padding-right: 12px !important;
}}

:where([data-testid="stMain"])
:where([data-testid="stTextAreaRootElement"] textarea) {{
    min-height: 70px !important;
    resize: vertical !important;
}}

:where([data-testid="stMain"])
:where(
    [data-testid="stTextInputRootElement"] input,
    [data-testid="stTextAreaRootElement"] textarea,
    .react-aria-ComboBox input
)::placeholder {{
    color: var(--placeholder) !important;
    -webkit-text-fill-color: var(--placeholder) !important;
    opacity: 1 !important;
}}

/* Dropdown arrow */
:where([data-testid="stMain"])
:where(.react-aria-ComboBox, div[data-baseweb="select"]) svg {{
    color: var(--text-disabled) !important;
}}

/* Hover (editable controls only) */
:where([data-testid="stMain"])
:where(
    [data-testid="stTextInputRootElement"],
    [data-testid="stTextAreaRootElement"],
    .react-aria-ComboBox > [role="group"],
    div[data-baseweb="select"] > div
):not(:has(:disabled)):hover {{
    border-color: var(--control-border-hover) !important;
}}

/* Focus */
:where([data-testid="stMain"])
:where(
    [data-testid="stTextInputRootElement"],
    [data-testid="stTextAreaRootElement"],
    .react-aria-ComboBox > [role="group"],
    div[data-baseweb="select"] > div
):focus-within {{
    border-color: var(--axiom-purple) !important;
    box-shadow: 0 0 0 1px var(--axiom-purple) !important;
}}

/*
   Read-only controls keep the same box as editable ones and are
   told apart by muted text and no hover state. Borders are left
   alone so required read-only fields keep their status colour.
*/
:where([data-testid="stMain"])
:where(
    [data-testid="stTextInputRootElement"] input,
    [data-testid="stTextAreaRootElement"] textarea,
    .react-aria-ComboBox input,
    div[data-baseweb="select"] input
):disabled,
:where([data-testid="stMain"])
:where(div[data-baseweb="select"]:has(input:disabled)) span {{
    color: var(--text-disabled) !important;
    -webkit-text-fill-color: var(--text-disabled) !important;
    cursor: default !important;
}}


/* ================================================================
   FORM ROW ALIGNMENT AND SPACING
================================================================ */

/*
   Reduce Streamlit's default vertical spacing within expanders.
   Do not change column backgrounds or remove widget borders.
*/

div[data-testid="stExpanderDetails"]
div[data-testid="stVerticalBlock"] {{
    gap: 0.5rem !important;
}}

/*
   st.markdown blocks that only carry a <style> tag (the theme and
   apply_required_widget_state) render as empty element containers
   that still take a flex gap. Remove them from layout; their CSS
   keeps applying.
*/
[data-testid="stMain"]
[data-testid="stElementContainer"]:has(> [data-testid="stMarkdown"] style):not(
    :has([data-testid="stMarkdownContainer"] > :not(style))
) {{
    display: none !important;
}}

div[data-testid="stExpanderDetails"]
div[data-testid="stHorizontalBlock"] {{
    align-items: flex-start !important;
}}

/* Equal label height across columns in multi-column form rows */
:is(div[data-testid="stExpanderDetails"], .st-key-request_details_card)
div[data-testid="stHorizontalBlock"]
[data-testid="stWidgetLabel"] {{
    min-height: 2.5rem !important;
    align-items: flex-end !important;
}}

/*
   Keep controls on one line when a label wraps past the reserved
   height: columns stretch to the tallest one and each field's label
   absorbs the extra space, so the controls end up bottom-aligned.
   Assumes one field per column, as the form renderers lay them out.
   Rows with a textarea keep top alignment; bottom-aligning would
   drop the single-line controls to the textarea's bottom edge.
*/
:is(div[data-testid="stExpanderDetails"], .st-key-request_details_card)
div[data-testid="stHorizontalBlock"]:not(:has(textarea)) {{
    align-items: stretch !important;
}}

:is(div[data-testid="stExpanderDetails"], .st-key-request_details_card)
div[data-testid="stHorizontalBlock"]:not(:has(textarea))
> [data-testid="stColumn"] > [data-testid="stVerticalBlock"] {{
    height: 100% !important;
}}

:is(div[data-testid="stExpanderDetails"], .st-key-request_details_card)
div[data-testid="stHorizontalBlock"]:not(:has(textarea))
> [data-testid="stColumn"] > [data-testid="stVerticalBlock"]
> [data-testid="stElementContainer"]:has([data-testid="stWidgetLabel"]),
:is(div[data-testid="stExpanderDetails"], .st-key-request_details_card)
div[data-testid="stHorizontalBlock"]:not(:has(textarea))
> [data-testid="stColumn"] > [data-testid="stVerticalBlock"]
> [data-testid="stElementContainer"]:has([data-testid="stWidgetLabel"])
> div {{
    flex: 1 1 auto !important;
    display: flex !important;
    flex-direction: column !important;
}}

:is(div[data-testid="stExpanderDetails"], .st-key-request_details_card)
div[data-testid="stHorizontalBlock"]:not(:has(textarea))
[data-testid="stWidgetLabel"] {{
    flex: 1 1 auto !important;
}}

div[data-testid="stExpanderDetails"]
div[data-testid="stDivider"] {{
    margin-top: 0.15rem !important;
    margin-bottom: 0.15rem !important;
}}

div[data-testid="stExpanderDetails"] h5 {{
    margin-top: 0.2rem !important;
    margin-bottom: 0.1rem !important;
}}

div[data-testid="stExpanderDetails"]
[data-testid="stCaptionContainer"] {{
    margin-top: 0 !important;
    margin-bottom: 0.15rem !important;
}}

div[data-testid="stExpanderDetails"]
[data-testid="stMarkdown"] p {{
    margin-bottom: 0.1rem !important;
}}


/* ================================================================
   REQUEST DETAILS BUSINESS CARD
================================================================ */

div[data-testid="stVerticalBlockBorderWrapper"] {{
    box-sizing: border-box !important;
}}

[data-testid="column"]
> div > div
> div[data-testid="stVerticalBlockBorderWrapper"] {{
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-card) !important;
    box-shadow: var(--shadow-card) !important;
    padding: 0.9rem 1rem 1rem 1rem !important;
}}

div[data-testid="stVerticalBlockBorderWrapper"]
div[data-testid="stVerticalBlockBorderWrapper"] {{
    background: transparent !important;
    border: 0 !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    padding: 0 !important;
}}


/* ================================================================
   REQUEST DETAILS TITLE
================================================================ */

.panel-card-title {{
    display: flex;
    align-items: center;
    gap: 0.55rem;
    width: 100%;
    box-sizing: border-box;
    color: var(--text-strong) !important;
    font-size: 0.98rem !important;
    line-height: 1.25rem !important;
    font-weight: 750 !important;
    letter-spacing: -0.012em;
    padding: 0.05rem 0 0.65rem 0;
    margin: 0 0 0.1rem 0;
    border-bottom: 1px solid var(--border-light);
}}

.panel-card-icon {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.5rem;
    height: 1.5rem;
    flex: 0 0 1.5rem;
    border-radius: 6px;
    background: #EEF2F5;
    color: #41586C;
    font-size: 0.82rem;
    font-weight: 800;
}}


/* ================================================================
   EXISTING CUSTOMER CARD
================================================================ */

.customer-card {{
    box-sizing: border-box;
    width: 100%;
    margin: 0 !important;
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius-card) !important;
    box-shadow: var(--shadow-card) !important;
    overflow: hidden !important;
}}

.customer-card-title {{
    display: flex;
    align-items: center;
    gap: 0.55rem;
    color: var(--text-strong) !important;
    font-size: 0.96rem !important;
    line-height: 1.2rem !important;
    font-weight: 750 !important;
    letter-spacing: -0.012em;
    padding: 0.72rem 0.88rem 0.65rem;
    border-bottom: 1px solid var(--border-light);
}}

.customer-card-icon {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 1.5rem;
    height: 1.5rem;
    border-radius: 6px;
    background: #EEF2F5;
    color: #41586C;
    font-size: 0.82rem;
    font-weight: 800;
}}

.customer-card-grid {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    column-gap: 1.15rem;
    row-gap: 0;
    padding: 0.58rem 0.88rem 0.72rem;
}}

.customer-card-item {{
    box-sizing: border-box;
    min-width: 0;
    padding: 0.3rem 0;
}}

.customer-card-label {{
    display: block;
    color: #74808A !important;
    font-size: 0.68rem !important;
    line-height: 0.9rem !important;
    font-weight: 600 !important;
    margin-bottom: 0.06rem;
}}

.customer-card-value {{
    display: block;
    color: var(--text) !important;
    font-size: 0.78rem !important;
    line-height: 1.05rem !important;
    font-weight: 600 !important;
    overflow-wrap: anywhere;
}}

.customer-info-section {{
    padding: 0.65rem 0.88rem;
    border-bottom: 1px solid #F0F1F3;
}}

.customer-info-section:last-child {{
    border-bottom: none;
}}

.customer-info-heading {{
    color: #344956;
    font-size: 0.78rem;
    font-weight: 750;
    margin-bottom: 0.4rem;
}}

.customer-info-section .customer-card-grid {{
    padding: 0;
    column-gap: 0.9rem;
    row-gap: 0.3rem;
}}

.customer-info-section .customer-card-item {{
    padding: 0.15rem 0;
}}

.customer-info-section .customer-card-label {{
    font-size: 0.66rem;
    margin-bottom: 0.12rem;
}}

.customer-info-section .customer-card-value {{
    font-size: 0.78rem;
    line-height: 1.15rem;
}}


/* ================================================================
   EXPANDERS
================================================================ */

div[data-testid="stExpander"] {{
    box-sizing: border-box !important;
    width: 100% !important;
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-left: 5px solid #AEB7BE !important;
    border-radius: var(--radius-card) !important;
    box-shadow: var(--shadow-card) !important;
    overflow: hidden !important;
    margin: 0 !important;
}}

div[data-testid="stExpander"] details {{
    border: 0 !important;
    outline: 0 !important;
    box-shadow: none !important;
}}

div[data-testid="stExpander"] details > summary {{
    box-sizing: border-box !important;
    min-height: 48px !important;
    display: flex !important;
    align-items: center !important;
    padding: 0.62rem 0.85rem !important;
    background: #F7F8F9 !important;
    color: var(--text) !important;
    border: 0 !important;
    outline: 0 !important;
    box-shadow: none !important;
    border-radius: 0 !important;
    font-weight: 700 !important;
}}

div[data-testid="stExpander"]
details > summary:hover {{
    filter: brightness(0.99);
}}

div[data-testid="stExpander"]
details > summary:focus,
div[data-testid="stExpander"]
details > summary:focus-visible {{
    outline: 0 !important;
    box-shadow: none !important;
}}

div[data-testid="stExpander"]
details > summary p,
div[data-testid="stExpander"]
details > summary span {{
    color: var(--text) !important;
    font-size: 0.88rem !important;
    font-weight: 700 !important;
}}

div[data-testid="stExpander"]
details > summary svg {{
    color: #50606B !important;
}}

div[data-testid="stExpander"]
details[open] > summary {{
    border-bottom: 1px solid var(--border-light) !important;
}}

div[data-testid="stExpanderDetails"] {{
    box-sizing: border-box !important;
    background: var(--surface) !important;
    padding-top: 0.75rem !important;
    padding-bottom: 0.8rem !important;
}}


/* ================================================================
   CAPTIONS
================================================================ */

[data-testid="stCaptionContainer"] p {{
    color: var(--muted) !important;
    font-size: 0.76rem !important;
    line-height: 1.15rem !important;
}}


/* ================================================================
   PRIMARY BUTTONS
================================================================ */

[data-testid="stMain"]
button[kind="primary"],
[data-testid="stMain"]
button[data-testid="stBaseButton-primary"] {{
    box-sizing: border-box !important;
    min-height: 40px !important;
    border-radius: 7px !important;
    background: var(--axiom-purple) !important;
    border: 1px solid var(--axiom-purple) !important;
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
    font-size: 0.82rem !important;
    font-weight: 650 !important;
    padding-left: 1.15rem !important;
    padding-right: 1.15rem !important;
    box-shadow: none !important;
    transition:
        background-color 0.12s ease,
        border-color 0.12s ease !important;
}}

[data-testid="stMain"]
button[kind="primary"] *,
[data-testid="stMain"]
button[data-testid="stBaseButton-primary"] * {{
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
}}

[data-testid="stMain"]
button[kind="primary"]:hover,
[data-testid="stMain"]
button[data-testid="stBaseButton-primary"]:hover {{
    background: var(--axiom-purple-hover) !important;
    border-color: var(--axiom-purple-hover) !important;
    color: #FFFFFF !important;
}}

[data-testid="stMain"]
button[kind="primary"]:focus-visible,
[data-testid="stMain"]
button[data-testid="stBaseButton-primary"]:focus-visible {{
    box-shadow: 0 0 0 2px rgba(102, 59, 255, 0.16) !important;
}}


/* ================================================================
   SECONDARY BUTTONS
================================================================ */

[data-testid="stMain"]
button[kind="secondary"],
[data-testid="stMain"]
button[data-testid="stBaseButton-secondary"] {{
    min-height: 40px !important;
    background: #FFFFFF !important;
    color: var(--text-strong) !important;
    border: 1px solid #D5DCE1 !important;
    border-radius: var(--radius-control) !important;
    font-size: 0.82rem !important;
    font-weight: 650 !important;
    box-shadow: none !important;
    transition:
        border-color 0.12s ease,
        background-color 0.12s ease,
        color 0.12s ease !important;
}}

[data-testid="stMain"]
button[kind="secondary"]:hover,
[data-testid="stMain"]
button[data-testid="stBaseButton-secondary"]:hover {{
    background: var(--axiom-purple-soft) !important;
    border-color: var(--axiom-purple) !important;
    color: var(--axiom-purple) !important;
}}


/* ================================================================
   REQUEST TYPE SEGMENTED CONTROL
================================================================ */

div[data-testid="stSegmentedControl"] button {{
    min-height: 42px !important;
    border-radius: 9px !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    color: #343447 !important;
    background: #FFFFFF !important;
    border: 1px solid #DCDCE8 !important;
    box-shadow: none !important;
}}

div[data-testid="stSegmentedControl"]
button[aria-checked="true"],
div[data-testid="stSegmentedControl"]
button[aria-pressed="true"],
div[data-testid="stSegmentedControl"]
button[aria-selected="true"] {{
    background: var(--axiom-purple) !important;
    border-color: var(--axiom-purple) !important;
    color: #FFFFFF !important;
}}

div[data-testid="stSegmentedControl"]
button[aria-checked="true"] *,
div[data-testid="stSegmentedControl"]
button[aria-pressed="true"] *,
div[data-testid="stSegmentedControl"]
button[aria-selected="true"] * {{
    color: #FFFFFF !important;
    -webkit-text-fill-color: #FFFFFF !important;
}}


/* ================================================================
   FILE UPLOADER
================================================================ */

[data-testid="stFileUploader"] {{
    width: 100% !important;
}}

[data-testid="stFileUploaderDropzone"] {{
    background: #FAFBFC !important;
    border: 1px dashed #C9D1D7 !important;
    border-radius: var(--radius-control) !important;
}}


/* ================================================================
   ALERTS AND PREREQUISITES
================================================================ */

[data-testid="stAlert"] {{
    border-radius: var(--radius-control) !important;
}}

.prerequisite-note {{
    box-sizing: border-box;
    width: 100%;
    color: var(--muted);
    background: #F7F8FA;
    border: 1px solid var(--border-light);
    border-radius: var(--radius-control);
    padding: 0.7rem 0.8rem;
    font-size: 0.78rem;
    line-height: 1.15rem;
}}


/* ================================================================
   DIVIDERS
================================================================ */

[data-testid="stMain"] hr {{
    border-color: var(--border-light) !important;
}}


/* ================================================================
   SPACING BETWEEN EXPANDERS
================================================================ */

div[data-testid="stVerticalBlock"]:has(
    > div > div[data-testid="stExpander"]
) {{
    gap: 0.45rem !important;
}}

/* ================================================================
   RESPONSIVE LAYOUT
================================================================ */

@media (max-width: 1100px) {{

    section[data-testid="stMain"]
    [data-testid="stMainBlockContainer"] {{
        padding-left: 0.85rem !important;
        padding-right: 0.85rem !important;
    }}

}}

@media (max-width: 900px) {{

    section[data-testid="stMain"]
    [data-testid="stMainBlockContainer"] {{
        padding-top: 0.3rem !important;
        padding-left: 0.65rem !important;
        padding-right: 0.65rem !important;
    }}

    .customer-card-grid {{
        grid-template-columns: 1fr !important;
    }}

}}


</style>
""",
        unsafe_allow_html=True,
    )


# =============================================================================
# WORKBENCH ADDITIONS
# =============================================================================

# Internal status -> (background, text colour) of its pill
STATUS_PILLS = {
    "NEEDS_REVIEW": ("#FFF8DD", "#8A6A00"),
    "IN_PROCESS": ("#F3EFFF", "#5429E8"),
    "WAITING_FOR_REQUESTER": ("#FFF1E6", "#B54708"),
    "ON_HOLD": ("#F2F4F7", "#475467"),
    "COMPLETED": ("#ECF7EE", "#2E7D32"),
}


def status_pill(status: str, label: str) -> str:
    background, color = STATUS_PILLS.get(status, STATUS_PILLS["ON_HOLD"])
    return (
        f'<span class="wb-pill" style="background:{background};color:{color};">'
        f"{label}</span>"
    )


def apply_workbench_styles() -> None:
    """Sidebar and request-list styles on top of apply_theme()."""
    st.markdown(
        """
<style>

/* ---------------- Sidebar (same gradient as the AXIOM portal) ---------------- */

section[data-testid="stSidebar"] {
    background:
        radial-gradient(circle at 10% 82%, rgba(111,76,255,0.28) 0%,
            rgba(111,76,255,0.10) 24%, transparent 48%),
        linear-gradient(180deg, #202747 0%, #252653 52%, #29235C 100%) !important;
    border-right: 1px solid rgba(255,255,255,0.06) !important;
}

section[data-testid="stSidebar"] > div,
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {
    background: transparent !important;
}

section[data-testid="stSidebar"] p,
section[data-testid="stSidebar"] span,
section[data-testid="stSidebar"] label {
    color: #E7E5F5 !important;
}

.wb-side-eyebrow {
    color: #B9B8D5 !important;
    font-size: 0.67rem;
    font-weight: 700;
    letter-spacing: 0.11em;
    margin: 0.2rem 0 0.35rem 0;
}

.wb-side-title {
    color: #FFFFFF !important;
    font-size: 1.05rem;
    font-weight: 700;
    margin-bottom: 0.9rem;
}

.wb-side-user {
    color: #B9B8D5 !important;
    font-size: 0.76rem;
    line-height: 1.15rem;
    overflow-wrap: anywhere;
}

.wb-side-user b {
    color: #FFFFFF;
    font-weight: 600;
}

.wb-side-card {
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(189,174,255,0.22);
    border-radius: 10px;
    padding: 0.7rem 0.8rem;
    margin: 0.6rem 0 0.9rem 0;
    font-size: 0.78rem;
    line-height: 1.15rem;
    color: #E7E5F5;
}

.wb-side-card b {
    color: #FFFFFF;
}

section[data-testid="stSidebar"] button {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(189,174,255,0.35) !important;
    color: #FFFFFF !important;
    border-radius: 8px !important;
}

section[data-testid="stSidebar"] button:hover {
    background: rgba(119,82,255,0.30) !important;
    border-color: #8B68FA !important;
}

section[data-testid="stSidebar"] button * {
    color: #FFFFFF !important;
}

/* ---------------- Header ---------------- */

.wb-header-title {
    color: var(--text-strong);
    font-size: 1.35rem;
    font-weight: 750;
    letter-spacing: -0.02em;
    line-height: 1.6rem;
}

.wb-header-sub {
    color: var(--muted);
    font-size: 0.82rem;
    margin-top: 0.15rem;
}

.wb-header-user {
    text-align: right;
}

/* ---------------- Request list ---------------- */

.wb-pill {
    display: inline-block;
    padding: 0.12rem 0.55rem;
    border-radius: 999px;
    font-size: 0.74rem;
    font-weight: 650;
    white-space: nowrap;
}

.wb-col-head p {
    color: var(--muted-light) !important;
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.08em;
    text-transform: uppercase;
}

.wb-request-id {
    font-weight: 700;
    color: var(--text-strong);
    font-size: 0.86rem;
}

.wb-muted {
    color: var(--muted);
    font-size: 0.82rem;
}

div[data-testid="stExpanderDetails"] [data-testid="stHorizontalBlock"] {
    align-items: center !important;
}

/* ---------------- Selected request ---------------- */

.wb-section-title {
    color: var(--text-strong);
    font-size: 1.05rem;
    font-weight: 750;
    margin: 0.4rem 0 0.2rem 0;
}

[data-testid="stMain"] [data-baseweb="tab-list"] button[aria-selected="true"] p,
[data-testid="stMain"] [role="tablist"] button[aria-selected="true"] p {
    color: var(--axiom-purple) !important;
    font-weight: 700 !important;
}

[data-testid="stMain"] [data-baseweb="tab-highlight"] {
    background-color: var(--axiom-purple) !important;
}

[data-testid="stMain"] [data-testid="stDownloadButton"] button {
    min-height: 40px !important;
    border-radius: var(--radius-control) !important;
    border: 1px solid var(--axiom-purple) !important;
    color: var(--axiom-purple) !important;
    background: #FFFFFF !important;
    font-weight: 650 !important;
}

[data-testid="stMain"] [data-testid="stDownloadButton"] button:hover {
    background: var(--axiom-purple-soft) !important;
}

</style>
""",
        unsafe_allow_html=True,
    )
