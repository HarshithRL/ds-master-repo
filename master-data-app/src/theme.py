from __future__ import annotations

from typing import Mapping

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

INPUT_BG = "#FFFFFF"
DISABLED_BG = "#F2F4F7"

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
    """
    Apply the Customer Master Data application theme

    """

    st.markdown(
        f"""
        <style>

        /* ================================================================
           VARIABLES
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

            --input-disabled-bg: #EEF2F5;
            --input-disabled-text: #526775;
            --input-bg: {INPUT_BG};
            --disabled-bg: {DISABLED_BG};

            --radius-card: 12px;
            --radius-control: 8px;
            
            --shadow-card:
                0 1px 3px rgba(16, 24, 40, 0.04),
                0 1px 2px rgba(16, 24, 40, 0.03);
 
        }}

        /* ================================================================
           STREAMLIT UI
           ================================================================ */

        header[data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        #MainMenu,
        footer {{
            display: none !important;
            visibility: hidden !important;
        }}

        /* ================================================================
           PAGE
           ================================================================ */

        html,
        body,
        [data-testid="stAppViewContainer"],
        .stApp {{
            background: var(--page) !important;
            color: var(--text) !important;
        }}

        [data-testid="stAppViewContainer"]
        [data-testid="stAppViewBlockContainer"] {{
            width: 100% !important;
            max-width: 1500px !important;

            padding-top: 0 !important;
            padding-right: 1.75rem !important;
            padding-bottom: 2.5rem !important;
            padding-left: 1.75rem !important;

            margin-top: 0 !important;
            margin-left: auto !important;
            margin-right: auto !important;
        }}

        /* Remove Streamlit space before first main element */

        [data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] {{
            gap: 0.75rem !important;
        }}

        /* ================================================================
           TYPOGRAPHY
           ================================================================ */

        body,
        input,
        textarea,
        button {{
            color: var(--text);
        }}

        p {{
            color: var(--text);
        }}
        

        /* ================================================================
           HEADER BRAND
           ================================================================ */

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
           COLUMN ALIGNMENT
           ================================================================ */

        [data-testid="column"] {{
            min-width: 0 !important;
        }}

        /* ================================================================
           LABELS
           ================================================================ */

        .stTextInput label,
        .stSelectbox label,
        .stTextArea label,
        .stFileUploader label,
        [data-testid="stWidgetLabel"] p {{
            color: #45545F !important;

            font-size: 0.82rem !important;
            line-height: 1.1rem !important;

            font-weight: 600 !important;
        }}

        /* ================================================================
           FORM CONTROLS: normal, hover, focus and disabled
           Validation rules in portal/ui_common.py are scoped by widget key.
           ================================================================ */
        .stTextInput div[data-baseweb="input"] > div,
        .stNumberInput div[data-baseweb="input"] > div,
        .stSelectbox div[data-baseweb="select"] > div {{
            min-height: 40px !important;
            background: var(--input-bg) !important;
            border: 1px solid var(--input-border) !important;
            border-radius: var(--radius-control) !important;
            box-shadow: none !important;
            transition: border-color .15s ease, box-shadow .15s ease;
        }}
        .stTextInput div[data-baseweb="input"] > div:hover,
        .stNumberInput div[data-baseweb="input"] > div:hover,
        .stSelectbox div[data-baseweb="select"] > div:hover {{
            border-color: var(--input-border-hover) !important;
        }}
        .stTextInput div[data-baseweb="input"]:focus-within > div,
        .stNumberInput div[data-baseweb="input"]:focus-within > div,
        .stSelectbox div[data-baseweb="select"]:focus-within > div {{
            border-color: var(--input-focus) !important;
            box-shadow: 0 0 0 2px rgba(39,51,61,.10) !important;
        }}
        .stTextArea textarea {{
            min-height: 72px !important;
            color: var(--text) !important;
            background: var(--input-bg) !important;
            border: 1px solid var(--input-border) !important;
            border-radius: var(--radius-control) !important;
            resize: vertical !important;
            box-shadow: none !important;
        }}
        .stTextArea textarea:hover {{ border-color: var(--input-border-hover) !important; }}
        .stTextArea textarea:focus {{
            border-color: var(--input-focus) !important;
            box-shadow: 0 0 0 2px rgba(39,51,61,.10) !important;
        }}
        .stTextInput input, .stNumberInput input {{ color: var(--text) !important; }}
        .stTextInput input:disabled, .stNumberInput input:disabled,
        .stTextArea textarea:disabled {{
            color: var(--input-disabled-text) !important;
            -webkit-text-fill-color: var(--input-disabled-text) !important;
            background: var(--input-disabled-bg) !important;
            opacity: 1 !important;
        }}

        /* ================================================================
           REQUEST DETAILS BUSINESS CARD
           ================================================================ */

        div[data-testid="stVerticalBlockBorderWrapper"] {{
            box-sizing: border-box !important;
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

            margin: 0.85rem 0 0 0 !important;

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

            padding:
                0.72rem
                0.88rem
                0.65rem
                0.88rem;

            border-bottom:
                1px solid var(--border-light);
        }}

        .customer-card-icon {{
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

        .customer-card-grid {{
            display: grid;

            grid-template-columns:
                repeat(2, minmax(0, 1fr));

            column-gap: 1.15rem;
            row-gap: 0;

            padding:
                0.58rem
                0.88rem
                0.72rem
                0.88rem;
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

        /* ================================================================
           EXPANDERS
           ================================================================ */

        div[data-testid="stExpander"] {{
            box-sizing: border-box !important;

            width: 100% !important;

            background: var(--surface) !important;

            border:
                1px solid
                var(--border)
                !important;

            border-left:
                5px solid
                #AEB7BE
                !important;

            border-radius:
                var(--radius-card)
                !important;

            box-shadow:
                var(--shadow-card)
                !important;

            overflow:
                hidden
                !important;

            margin:
                0
                0
                0.55rem
                0
                !important;
        }}

        /* Remove internal visual borders only from the expander itself. */

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

            padding:
                0.62rem
                0.85rem
                !important;

            background:
                #F7F8F9
                !important;

            color:
                var(--text)
                !important;

            border:
                0
                !important;

            outline:
                0
                !important;

            box-shadow:
                none
                !important;

            border-radius:
                0
                !important;

            font-weight:
                700
                !important;
        }}

        div[data-testid="stExpander"]
        details > summary:hover {{
            filter: brightness(0.99);
        }}

        div[data-testid="stExpander"]
        details > summary:focus,
        div[data-testid="stExpander"]
        details > summary:focus-visible {{
            border: 0 !important;
            outline: 0 !important;
            box-shadow: none !important;
        }}

        div[data-testid="stExpander"]
        details > summary p,
        div[data-testid="stExpander"]
        details > summary span {{
            color:
                var(--text)
                !important;

            font-size:
                0.88rem
                !important;

            font-weight:
                700
                !important;
        }}

        div[data-testid="stExpander"]
        details > summary svg {{
            color:
                #50606B
                !important;
        }}

        div[data-testid="stExpander"]
        details[open] > summary {{
            border-bottom:
                1px solid
                var(--border-light)
                !important;
        }}

        /* ================================================================
           EXPANDER CONTENT
           ================================================================ */

        div[data-testid="stExpanderDetails"] {{
            box-sizing: border-box !important;

            background:
                var(--surface)
                !important;

            padding-top:
                0.75rem
                !important;

            padding-bottom:
                0.8rem
                !important;
        }}

        /* ================================================================
           SUBHEADINGS INSIDE FORM
           ================================================================ */

        h3 {{
            color: var(--text-strong) !important;

            font-weight: 750 !important;
        }}


        h5 {{
            color: #344956 !important;

            font-size: 0.86rem !important;
            line-height: 1.1rem !important;

            font-weight: 700 !important;

            margin-top: 0.35rem !important;
            margin-bottom: 0.35rem !important;
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
           BUTTONS
           ================================================================ */

        button {{
            font-family: inherit !important;
        }}

        button[kind="primary"],
        button[data-testid="stBaseButton-primary"] {{
            box-sizing: border-box !important;

            min-height: 40px !important;

            border-radius: 7px !important;

            background: var(--axiom-purple) !important;
            border: 1px solid var(--axiom-purple) !important;

            color: #FFFFFF !important;

            font-size: 0.82rem !important;
            font-weight: 650 !important;

            padding-left: 1.15rem !important;
            padding-right: 1.15rem !important;

            box-shadow: none !important;

            transition:
                background-color 0.12s ease,
                border-color 0.12s ease !important;
        }}

        button[kind="primary"]:hover,
        button[data-testid="stBaseButton-primary"]:hover {{
            background: var(--axiom-purple-hover) !important;
            border-color: var(--axiom-purple-hover) !important;
                        color:
                            #FFFFFF
                            !important;
                    }}

        button[kind="primary"]:focus,
        button[data-testid="stBaseButton-primary"]:focus {{
            box-shadow:
                0 0 0 2px
                rgba(102, 59, 255, 0.16)
                !important;
        }}

        /* Secondary buttons */

        button[kind="secondary"],
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

        button[kind="secondary"]:hover,
        button[data-testid="stBaseButton-secondary"]:hover {{
            background: var(--axiom-purple-soft) !important;
            border-color: var(--axiom-purple) !important;
            color: var(--axiom-purple) !important;
        }}

        /* ================================================================
           FILE UPLOADER
           ================================================================ */

        [data-testid="stFileUploader"] {{
            width: 100% !important;
        }}

        [data-testid="stFileUploaderDropzone"] {{
            background:
                #FAFBFC
                !important;

            border:
                1px dashed
                #C9D1D7
                !important;

            border-radius:
                var(--radius-control)
                !important;
        }}

        /* ================================================================
           COMMENTS
           ================================================================ */

        .stTextArea textarea::placeholder {{
            color: #9BA4AC !important;
        }}

        /* ================================================================
           ALERTS
           ================================================================ */

        [data-testid="stAlert"] {{
            border-radius:
                var(--radius-control)
                !important;
        }}

        /* ================================================================
           PREREQUISITE MESSAGE
           ================================================================ */

        .prerequisite-note {{
            box-sizing: border-box;

            width: 100%;

            color: var(--muted);

            background: #F7F8FA;

            border:
                1px solid
                var(--border-light);

            border-radius:
                var(--radius-control);

            padding:
                0.7rem
                0.8rem;

            font-size:
                0.78rem;

            line-height:
                1.15rem;
        }}


        /* ================================================================
           DIVIDERS
           ================================================================ */

        hr {{
            border-color:
                var(--border-light)
                !important;
        }}

        /* ================================================================
           RESPONSIVE
           ================================================================ */

        @media (max-width: 1100px) {{

            [data-testid="stMainBlockContainer"] {{
                padding-left: 0.85rem !important;
                padding-right: 0.85rem !important;
            }}

        }}

        @media (max-width: 900px) {{

            [data-testid="stMainBlockContainer"] {{
                padding-top: 0 !important;
                padding-left: 0.65rem !important;
                padding-right: 0.65rem !important;
            }}


            .customer-card-grid {{
                grid-template-columns:
                    1fr
                    !important;
            }}

        }}

        </style>
        """,
        unsafe_allow_html=True,
    )


# =============================================================================
# SECTION STATUS COLOURS
# =============================================================================

def apply_section_statuses(statuses: Mapping[str, str]) -> None:
    """Color the five explicitly keyed section expanders; no positional selectors."""
    ordered_keys = (
        "general_data", "company_code", "sales_distribution",
        "partner_functions", "credit_management",
    )
    rules = []
    for key in ordered_keys:
        palette = STATUS.get(statuses.get(key, "neutral"), STATUS["neutral"])
        scope = f".st-key-{key}_section [data-testid=\"stExpander\"]"
        rules.append(f"{scope} {{ border-left-color: {palette['rail']} !important; }}")
        rules.append(f"{scope} details > summary {{ background: {palette['fill']} !important; }}")
    st.markdown("<style>" + "\n".join(rules) + "</style>", unsafe_allow_html=True)
