import streamlit as st
import pandas as pd
import uuid
import base64
from datetime import datetime


def _to_bool(series):
    """Convert column to bool — handles string 'True'/'False' from SQL connector."""
    if series.dtype == bool:
        return series
    return series.astype(str).str.lower() == "true"

# ============================================================
st.set_page_config(
    page_title="Air Monitoring Tool",
    page_icon="🌬️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

from utils.config import OUTPUT_TABLE, DEDUP_GRAIN, HIGH_CONC_THRESHOLD, VOLUME_PATH

# ════════════════════════════════════════════════════════════
# PREMIUM CSS — Modern glassmorphism + gradient design system
# ════════════════════════════════════════════════════════════
st.markdown("""
<style>
/* ─── ROOT VARIABLES ─── */
:root {
    --primary: #e8600a;
    --primary-dark: #c75000;
    --primary-light: #fff3e0;
    --accent: #0891b2;
    --accent-light: #cffafe;
    --success: #059669;
    --success-light: #d1fae5;
    --warning: #d97706;
    --warning-light: #fef3c7;
    --danger: #dc2626;
    --danger-light: #fee2e2;
    --surface: #ffffff;
    --surface-dim: #f8fafc;
    --border: #e2e8f0;
    --text: #1e293b;
    --text-muted: #64748b;
    --shadow-sm: 0 1px 2px rgba(0,0,0,0.05);
    --shadow: 0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05);
    --shadow-lg: 0 10px 15px -3px rgba(0,0,0,0.08), 0 4px 6px -4px rgba(0,0,0,0.04);
    --shadow-xl: 0 20px 25px -5px rgba(0,0,0,0.08), 0 8px 10px -6px rgba(0,0,0,0.04);
    --radius: 12px;
    --radius-lg: 16px;
    --radius-xl: 20px;
    --transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}


/* ─── HIDE SIDEBAR COMPLETELY ─── */
section[data-testid="stSidebar"] {
    display: none !important;
}
[data-testid="stSidebarCollapsedControl"] {
    display: none !important;
}
.block-container {
    padding: 1rem 2.5rem 5rem 2.5rem !important;
    max-width: 1500px;
}


/* ─── TYPOGRAPHY & FONTS ─── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

* {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
}

h1 {
    font-size: 1.85rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.8px !important;
    color: #0f172a !important;
    line-height: 1.2 !important;
}
h2 {
    font-size: 1.3rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.5px !important;
    color: #1e293b !important;
}
h3 {
    font-size: 1.05rem !important;
    font-weight: 600 !important;
    color: #334155 !important;
}
p, span:not(.app-title), label, div {
    font-size: 0.875rem !important;
    line-height: 1.6 !important;
}
.app-title {
    font-size: 1.75rem !important;
    font-weight: 900 !important;
    color: #0f172a !important;
    letter-spacing: -1px !important;
}

/* Center tabs */
.stTabs [data-baseweb="tab-list"] {
    justify-content: center !important;
}

/* Hide Streamlit native header and reposition */
header[data-testid="stHeader"] {
    display: none !important;
}
[data-testid="stToolbar"] {
    display: none !important;
}
.block-container {
    padding-top: 5rem !important;
}


/* Tab labels */
.stTabs [data-baseweb="tab"] {
    font-size: 0.88rem !important;
    font-weight: 600 !important;
    letter-spacing: -0.2px !important;
}

/* Metric values */
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 2rem !important;
    font-weight: 900 !important;
    letter-spacing: -1px !important;
    color: #0f172a !important;
}
div[data-testid="stMetric"] label {
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
    color: #64748b !important;
}

/* Buttons */
.stButton > button {
    font-size: 0.85rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.2px !important;
}

/* Selectbox / Input labels */
[data-testid="stSelectbox"] label,
[data-testid="stTextInput"] label,
[data-testid="stDateInput"] label,
[data-testid="stMultiSelect"] label,
[data-testid="stFileUploader"] label {
    font-size: 0.78rem !important;
    font-weight: 600 !important;
    color: #475569 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    margin-bottom: 4px !important;
}

/* Input values */
[data-testid="stSelectbox"] input,
[data-testid="stSelectbox"] [data-baseweb="select"] span,
[data-testid="stTextInput"] input {
    font-size: 0.88rem !important;
    font-weight: 500 !important;
    color: #1e293b !important;
}

/* Data editor / table cells */
[data-testid="stDataEditor"] td,
[data-testid="stDataFrame"] td {
    font-size: 0.82rem !important;
    font-weight: 400 !important;
}
[data-testid="stDataEditor"] th,
[data-testid="stDataFrame"] th {
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.5px !important;
    color: #64748b !important;
}

/* Captions */
.stCaption, [data-testid="stCaption"] {
    font-size: 0.78rem !important;
    color: #94a3b8 !important;
    font-weight: 400 !important;
}

/* Alert text */
[data-testid="stAlert"] p {
    font-size: 0.85rem !important;
    font-weight: 500 !important;
}

/* Hero section typography */
.hero-section h2 {
    font-size: 1.5rem !important;
    font-weight: 800 !important;
    letter-spacing: -0.5px !important;
    color: #f8fafc !important;
}
.hero-section p {
    font-size: 0.88rem !important;
    font-weight: 400 !important;
    color: #94a3b8 !important;
    letter-spacing: 0.1px !important;
}

/* Step indicator text */
.step-text {
    font-size: 0.88rem !important;
    font-weight: 600 !important;
    color: #1e293b !important;
    letter-spacing: -0.2px !important;
}

/* Badge text */
.badge {
    font-size: 0.7rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.6px !important;
}

/* Download button */
.stDownloadButton > button {
    font-size: 0.82rem !important;
    font-weight: 600 !important;
}

/* Expander header */
.streamlit-expanderHeader p {
    font-size: 0.88rem !important;
    font-weight: 600 !important;
}

/* Subheader */
[data-testid="stSubheader"] {
    font-size: 1.1rem !important;
    font-weight: 700 !important;
    letter-spacing: -0.3px !important;
    color: #1e293b !important;
}


/* ─── GLOBAL RESET ─── */
.block-container {
    padding: 2rem 2rem 3rem 2rem !important;
    max-width: 1400px;
}



/* ─── PAGE TITLES ─── */
h1 {
    color: var(--text) !important;
    font-weight: 800 !important;
    font-size: 2rem !important;
    letter-spacing: -1px !important;
    margin-bottom: 0.25rem !important;
}

/* ─── METRIC CARDS ─── */
div[data-testid="stMetric"] {
    background: var(--surface) !important;
    border: 1px solid var(--border) !important;
    border-radius: var(--radius) !important;
    padding: 1.25rem 1.5rem !important;
    box-shadow: var(--shadow) !important;
    transition: var(--transition) !important;
    position: relative;
    overflow: hidden;
}
div[data-testid="stMetric"]:hover {
    box-shadow: var(--shadow-lg) !important;
    transform: translateY(-2px);
    border-color: var(--primary-light) !important;
}
div[data-testid="stMetric"]::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
    background: linear-gradient(90deg, #e8600a, #f59e0b);
    border-radius: var(--radius) var(--radius) 0 0;
}
div[data-testid="stMetric"] label {
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.8px !important;
    color: var(--text-muted) !important;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.8rem !important;
    font-weight: 800 !important;
    color: var(--text) !important;
}

/* ─── BUTTONS ─── */
.stButton > button[kind="primary"],
.stButton > button[data-testid="baseButton-primary"] {
    background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%) !important;
    border: none !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
    letter-spacing: 0.3px !important;
    padding: 0.65rem 1.5rem !important;
    box-shadow: 0 4px 14px rgba(232, 96, 10, 0.25) !important;
    transition: var(--transition) !important;
}
.stButton > button[kind="primary"]:hover,
.stButton > button[data-testid="baseButton-primary"]:hover {
    box-shadow: 0 6px 20px rgba(232, 96, 10, 0.35) !important;
    transform: translateY(-1px) !important;
}
.stButton > button[kind="secondary"],
.stButton > button[data-testid="baseButton-secondary"] {
    border-radius: 10px !important;
    border: 1.5px solid var(--border) !important;
    font-weight: 500 !important;
    transition: var(--transition) !important;
}
.stButton > button[kind="secondary"]:hover,
.stButton > button[data-testid="baseButton-secondary"]:hover {
    border-color: var(--primary) !important;
    color: var(--primary) !important;
    background: var(--primary-light) !important;
}

/* ─── FILE UPLOADER ─── */
[data-testid="stFileUploader"] {
    border: 2px dashed var(--border) !important;
    border-radius: var(--radius-lg) !important;
    padding: 2rem !important;
    background: linear-gradient(135deg, var(--surface-dim) 0%, #f0f9ff 100%) !important;
    transition: var(--transition) !important;
}
[data-testid="stFileUploader"]:hover {
    border-color: var(--primary) !important;
    background: linear-gradient(135deg, var(--primary-light) 0%, #e0f2fe 100%) !important;
    box-shadow: 0 0 0 4px rgba(232, 96, 10, 0.08) !important;
}

/* ─── TABS ─── */
.stTabs [data-baseweb="tab-list"] {
    gap: 6px !important;
    background: var(--surface-dim);
    border-radius: var(--radius);
    padding: 4px;
    border: 1px solid var(--border);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 8px !important;
    padding: 10px 18px !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    transition: var(--transition) !important;
}
.stTabs [aria-selected="true"] {
    background: var(--surface) !important;
    box-shadow: var(--shadow-sm) !important;
    font-weight: 600 !important;
}

/* ─── DATA EDITOR / TABLES ─── */
[data-testid="stDataFrame"], [data-testid="stDataEditor"] {
    border-radius: var(--radius) !important;
    border: 1px solid var(--border) !important;
    box-shadow: var(--shadow-sm) !important;
    overflow: hidden;
}

/* ─── EXPANDER ─── */
.streamlit-expanderHeader {
    font-weight: 600 !important;
    font-size: 0.9rem !important;
    border-radius: var(--radius) !important;
}

/* ─── SELECTBOX / INPUT ─── */
[data-testid="stSelectbox"], [data-testid="stTextInput"] {
    transition: var(--transition);
}
[data-testid="stSelectbox"] > div > div,
[data-testid="stTextInput"] > div > div > input {
    border-radius: 10px !important;
    border: 1.5px solid var(--border) !important;
    transition: var(--transition) !important;
}
[data-testid="stSelectbox"] > div > div:focus-within,
[data-testid="stTextInput"] > div > div > input:focus {
    border-color: var(--primary) !important;
    box-shadow: 0 0 0 3px rgba(232, 96, 10, 0.1) !important;
}

/* ─── STATUS WIDGET ─── */
[data-testid="stStatus"] {
    border-radius: var(--radius) !important;
    border: 1px solid var(--border) !important;
}

/* ─── PROGRESS BAR ─── */
.stProgress > div > div > div {
    background: linear-gradient(90deg, #e8600a, #f59e0b) !important;
    border-radius: 8px !important;
}

/* ─── ALERTS ─── */
[data-testid="stAlert"] {
    border-radius: var(--radius) !important;
    border: none !important;
    box-shadow: var(--shadow-sm) !important;
}

/* ─── CUSTOM CLASSES ─── */
.hero-section {
    background: linear-gradient(135deg, #1a1a2e 0%, #2d2d44 50%, #3d2000 100%);
    border-radius: var(--radius-xl);
    padding: 2rem 2rem;
    margin-bottom: 1.5rem;
    position: relative;
    overflow: hidden;
    min-height: 100px;
}
.hero-section::before {
    content: '';
    position: absolute;
    top: -50%;
    right: -20%;
    width: 400px;
    height: 400px;
    background: radial-gradient(circle, rgba(232, 96, 10, 0.12) 0%, transparent 70%);
    border-radius: 50%;
}
.hero-section h2 {
    color: #f1f5f9 !important;
    font-size: 1.6rem !important;
    font-weight: 700 !important;
    margin-bottom: 0.5rem !important;
}
.hero-section p {
    color: #94a3b8 !important;
    font-size: 0.95rem !important;
    margin: 0 !important;
}

.card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    padding: 1.5rem;
    box-shadow: var(--shadow);
    transition: var(--transition);
}
.card:hover {
    box-shadow: var(--shadow-lg);
}

.badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.badge-success { background: var(--success-light); color: var(--success); }
.badge-warning { background: var(--warning-light); color: var(--warning); }
.badge-danger { background: var(--danger-light); color: var(--danger); }
.badge-info { background: var(--primary-light); color: var(--primary); }

.dup-box {
    background: var(--warning-light);
    border-left: 4px solid var(--warning);
    border-radius: 0 var(--radius) var(--radius) 0;
    padding: 14px 18px;
    margin: 8px 0;
    font-size: 0.85rem;
    transition: var(--transition);
}
.dup-box:hover {
    box-shadow: var(--shadow);
    transform: translateX(2px);
}
.dup-existing { color: #92400e; font-weight: 600; }

.save-summary {
    background: linear-gradient(135deg, var(--success-light) 0%, #ecfdf5 100%);
    border: 1px solid #a7f3d0;
    border-radius: var(--radius-lg);
    padding: 1.5rem 2rem;
    text-align: center;
}

.pdf-container {
    border: 1px solid var(--border);
    border-radius: var(--radius-lg);
    overflow: hidden;
    box-shadow: var(--shadow-lg);
    background: #f8fafc;
}

.step-indicator {
    display: flex;
    align-items: center;
    gap: 12px;
    margin: 1rem 0;
    padding: 0.75rem 1rem;
    background: var(--surface-dim);
    border-radius: var(--radius);
    border: 1px solid var(--border);
}
.step-number {
    width: 28px;
    height: 28px;
    border-radius: 50%;
    background: linear-gradient(135deg, #e8600a, #f59e0b);
    color: white;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.8rem;
    font-weight: 700;
    flex-shrink: 0;
}
.step-text {
    font-size: 0.88rem;
    font-weight: 500;
    color: var(--text);
}

.metric-highlight {
    background: linear-gradient(135deg, #fef3c7 0%, #fffbeb 100%);
    border: 1px solid #fcd34d;
    border-radius: var(--radius);
    padding: 8px 14px;
    display: inline-block;
}

/* ─── SCROLLBAR ─── */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #94a3b8; }



/* ─── TOP NAV TABS ─── */
div[data-testid="stHorizontalBlock"]:first-of-type .stButton > button {
    background: transparent !important;
    border: none !important;
    border-bottom: 3px solid transparent !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    color: var(--text-muted) !important;
    font-weight: 500 !important;
    font-size: 0.9rem !important;
    padding: 0.75rem 1rem !important;
    transition: var(--transition) !important;
}
div[data-testid="stHorizontalBlock"]:first-of-type .stButton > button:hover {
    color: var(--primary) !important;
    border-bottom-color: var(--primary) !important;
    background: var(--primary-light) !important;
    transform: none !important;
    box-shadow: none !important;
}
div[data-testid="stHorizontalBlock"]:first-of-type .stButton > button:focus {
    color: var(--primary) !important;
    border-bottom-color: var(--primary) !important;
    box-shadow: none !important;
}



/* ─── STATUS TAG COLORS ─── */
span[data-baseweb="tag"] {
    border-radius: 6px !important;
    font-weight: 600 !important;
}
span[data-baseweb="tag"]:has(span[title="active"]) {
    background-color: #d1fae5 !important;
    border-color: #059669 !important;
}
span[data-baseweb="tag"]:has(span[title="active"]) span {
    color: #065f46 !important;
}
span[data-baseweb="tag"]:has(span[title="modified"]) {
    background-color: #fef3c7 !important;
    border-color: #d97706 !important;
}
span[data-baseweb="tag"]:has(span[title="modified"]) span {
    color: #92400e !important;
}
span[data-baseweb="tag"]:has(span[title="removed"]) {
    background-color: #fee2e2 !important;
    border-color: #dc2626 !important;
}
span[data-baseweb="tag"]:has(span[title="removed"]) span {
    color: #991b1b !important;
}

/* ─── DIVIDER ─── */
hr {
    border: none !important;
    height: 1px !important;
    background: linear-gradient(90deg, transparent, var(--border), transparent) !important;
    margin: 2rem 0 !important;
}
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════
# USER ID
# ════════════════════════════════════════════════════════════
def get_current_user() -> str:
    try:
        headers = st.context.headers if hasattr(st, 'context') else {}
        for key in ("X-Forwarded-Email", "X-Forwarded-User", "x-forwarded-email"):
            if key in headers:
                return headers[key]
    except:
        pass
    try:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient()
        me = w.current_user.me()
        return me.user_name or me.display_name or "unknown"
    except:
        return "unknown"


# ════════════════════════════════════════════════════════════
# SIDEBAR
# ════════════════════════════════════════════════════════════
# TOP HEADER — Logo left, App name, User right (NO SIDEBAR)
# ════════════════════════════════════════════════════════════
import os

user = get_current_user()
_initials = ""
if user != "unknown":
    _initials = "".join([p[0].upper() for p in user.split("@")[0].split(".")[:2]]) if "." in user else user[0:2].upper()

_LOGO_B64 = "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"

_user_section = ""
if user != "unknown":
    _user_section = (
        f'<div style="display:flex;align-items:center;gap:9px;">'
        f'<span style="color:#4a5568;font-size:0.85rem;font-weight:500;">{user.split("@")[0]}</span>'
        f'<div style="width:34px;height:34px;border-radius:50%;background:linear-gradient(135deg,#e8600a,#f59e0b);'
        f'display:flex;align-items:center;justify-content:center;color:white;font-size:0.78rem;font-weight:700;">{_initials}</div>'
        f'</div>'
    )

st.markdown(
    f'<div style="position:fixed;top:0;left:0;right:0;z-index:999;display:flex;justify-content:space-between;align-items:center;padding:0.6rem 2rem;background:white;border-bottom:1px solid #e8e8e8;box-shadow:0 1px 3px rgba(0,0,0,0.04);">'
    f'<div style="display:flex;align-items:center;gap:12px;">'
    f'<img src="data:image/jpeg;base64,{_LOGO_B64}" style="height:44px; object-fit:contain;" />'
    f'<span class="app-title">Air Monitoring Tool</span>'
    f'</div>'
    f'{_user_section}'
    f'</div>',
    unsafe_allow_html=True
)

# SESSION STATE
# ════════════════════════════════════════════════════════════
for key, default in [
    ("pdf_results", {}), ("processing_done", False),
    ("saved_files", set()), ("skipped_files", set()), ("duplicates_info", {}),
    ("batch_id", ""), ("volume_paths", {}),
    ("pdf_bytes", {}),
]:
    if key not in st.session_state:
        st.session_state[key] = default


# ════════════════════════════════════════════════════════════
# HELPERS
# ════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600)
def load_all_sites():
    from utils.db_utils import get_sites
    return get_sites()

def get_sites_for_user(user_email: str) -> pd.DataFrame:
    """Filter sites to only those the current user has access to.
    Admins bypass the filter and see all sites.
    """
    try:
        all_sites = load_all_sites()
        if all_sites.empty:
            return all_sites
        
        # If user unknown, show nothing (safety)
        if not user_email or user_email == "unknown":
            return pd.DataFrame(columns=["site_name", "site_code", "address", "allowed_users"])
        
        # Admins see all sites
        if is_admin(user_email):
            return all_sites.copy()
        
        # Filter: user email must be in the slash-separated allowed_users list
        user_lower = user_email.lower().strip()
        mask = all_sites["allowed_users"].fillna("").apply(
            lambda x: user_lower in [e.strip().lower() for e in str(x).split("/")]
        )
        filtered = all_sites[mask].copy()
        return filtered
    except Exception as e:
        st.error(f"Could not load sites: {e}")
        return pd.DataFrame(columns=["site_name", "site_code", "address", "allowed_users"])

def check_file_already_uploaded(filename: str, site_code: str) -> bool:
    """Check if this exact filename was already uploaded for this site."""
    from utils.db_utils import execute_query
    from utils.config import UPLOAD_LOG_TABLE
    safe_filename = filename.replace("'", "")
    result = execute_query(
        f"SELECT COUNT(*) as cnt FROM {UPLOAD_LOG_TABLE} "
        f"WHERE filename = '{safe_filename}' AND site_code = '{site_code}' AND status = 'success'"
    )
    if result is not None and not result.empty:
        return int(result.iloc[0]["cnt"]) > 0
    return False

def get_allowed_site_codes(user_email: str) -> list:
    """Get list of site_codes the user is allowed to see."""
    sites = get_sites_for_user(user_email)
    if sites.empty:
        return []
    return sites["site_code"].dropna().tolist()


# ────────────────────────────────────────────────────────────
# ADMIN
# ────────────────────────────────────────────────────────────
ADMIN_USERS = {
    "chiara.senzolo@etexgroup.com",
    "sofie.staes@etexgroup.com",
    "mustafaarda.bicakci@etexgroup.com",
}

def is_admin(user_email: str) -> bool:
    return user_email.lower().strip() in ADMIN_USERS

def render_pdf_preview(pdf_bytes: bytes, height: int = 550):
    b64 = base64.b64encode(pdf_bytes).decode("utf-8")
    st.markdown(
        f'<div class="pdf-container">'
        f'<iframe src="data:application/pdf;base64,{b64}" '
        f'width="100%" height="{height}px" style="border:none;"></iframe>'
        f'</div>',
        unsafe_allow_html=True
    )


# ════════════════════════════════════════════════════════════
# TOP NAVIGATION TABS
# ════════════════════════════════════════════════════════════
tab_upload, tab_browser, tab_history, tab_admin = st.tabs(["📤  Upload & Process", "📊  Output Browser", "📈  Analytics", "⚙️  Admin"])

# ════════════════════════════════════════════════════════════
# PAGE 1: UPLOAD & PROCESS
# ════════════════════════════════════════════════════════════
with tab_upload:


        # Hero
        st.markdown(
            '<div class="hero-section">'
            '<h2>Upload & Process Reports</h2>'
            '<p>Upload air monitoring reports, review AI extracted results, save to database</p>'
            '</div>',
            unsafe_allow_html=True
        )

        # ── Site Selection ──
        sites_df = get_sites_for_user(user)
        if sites_df.empty:
            st.error("Cannot connect to database. Please try again later.")
            st.stop()

        sites_df["display"] = sites_df["site_code"].fillna("") + " — " + sites_df["site_name"]

        st.markdown(
            '<div class="step-indicator"><div class="step-number">1</div><div class="step-text">Select the site</div></div>',
            unsafe_allow_html=True
        )
        selected = st.selectbox(
            "Site",
            options=sites_df["display"].tolist(),
            index=None,
            placeholder="Type to search by name or code...",
            label_visibility="collapsed"
        )

        site_info = {}
        if selected:
            match = sites_df[sites_df["display"] == selected].iloc[0]
            site_info = {
                "Site_name": match["site_name"],
                "Code": match["site_code"],
                "Site_Address": match.get("address", ""),
            }
            st.markdown(
                f'<div class="card" style="padding:1rem 1.25rem;margin-top:0.5rem;">'
                f'<span style="font-weight:700;color:var(--text);">{site_info["Site_name"]}</span>'
                f'<span class="badge badge-info" style="margin-left:10px;">{site_info["Code"]}</span>'
                f'<span style="color:var(--text-muted);font-size:0.82rem;margin-left:12px;">{site_info["Site_Address"] or ""}</span>'
                f'</div>',
                unsafe_allow_html=True
            )

        # ── Upload ──
        st.markdown("")
        st.markdown(
            '<div class="step-indicator"><div class="step-number">2</div><div class="step-text">Upload PDF reports</div></div>',
            unsafe_allow_html=True
        )
        uploaded_files = st.file_uploader(
            "Upload Reports (PDF only — other formats will be skipped)",
            type=None,
            accept_multiple_files=True,
            label_visibility="collapsed",
            help="Drag and drop multiple PDFs. Each file gets its own review tab."
        )

        if uploaded_files and site_info:
            file_list = " ".join([f'<span class="badge badge-info">{f.name}</span>' for f in uploaded_files])
            st.markdown(f'<div style="margin-top:8px;">{file_list}</div>', unsafe_allow_html=True)

        # ── Process ──
        st.markdown("")
        st.markdown(
            '<div class="step-indicator"><div class="step-number">3</div><div class="step-text">Process with AI</div></div>',
            unsafe_allow_html=True
        )

        can_process = bool(uploaded_files and site_info)
        if not can_process and not st.session_state.processing_done:
            if not site_info:
                st.info("Select a site to begin.")
            elif not uploaded_files:
                st.info("Upload at least one PDF file.")

        if st.button("🚀 Process All Reports", disabled=not can_process, type="primary", use_container_width=True):
            st.session_state.pdf_results = {}
            st.session_state.processing_done = False
            st.session_state.saved_files = set()
            st.session_state.duplicates_info = {}
            st.session_state.batch_id = str(uuid.uuid4())[:8]
            st.session_state.volume_paths = {}
            st.session_state.pdf_bytes = {}

            with st.status("Processing reports...", expanded=True) as status:
                _skipped_files = []
                for i, uf in enumerate(uploaded_files):
                    st.write(f"**[{i+1}/{len(uploaded_files)}]** `{uf.name}`")

                    # Check if this file was already uploaded for this site
                    if check_file_already_uploaded(uf.name, site_info["Code"]):
                        st.warning(f"  ⚠️ `{uf.name}` has already been uploaded for this site — skipping.")
                        _skipped_files.append(uf.name)
                        continue

                    if not uf.name.lower().endswith(".pdf"):
                        st.warning(f"  ⚠️ `{uf.name}` is not a PDF — skipped. Only PDF files can be processed.")
                        _skipped_files.append(uf.name)
                        continue

                    pdf_data = uf.getvalue()
                    st.session_state.pdf_bytes[uf.name] = pdf_data

                    volume_path = ""  # Volume upload disabled (no files scope needed)

                    try:
                        from utils.doc_intelligence import extract_from_pdf
                        raw = extract_from_pdf(pdf_data)
                        st.write(f"  ↳ Extracted ({len(raw.get('tables',[]))} tables)")
                    except Exception as e:
                        st.error(f"  ✗ Extraction failed: {e}")
                        continue

                    try:
                        from utils.llm_processor import parse_extraction, convert_concentration_to_f_ml
                        records = parse_extraction(raw, document_name=uf.name)
                        st.write(f"  ↳ **{len(records)} sample(s)** parsed")

                        for r in records:
                            r["Site_name"] = site_info["Site_name"]
                            r["Code"] = site_info["Code"]
                            r["Site_Address"] = site_info["Site_Address"]
                            r["upload_date"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            r["Document_name"] = uf.name
                            r["PDF_URL"] = volume_path
                            r["Concentration_result_in_f_ml"] = convert_concentration_to_f_ml(
                                r.get("Concentration_result", ""), r.get("Concentration_unit", "")
                            )
                            r["Flag_EM_Concentration"] = 1.0 if r.get("Analysis_method") == "Electron Microscopy" else 0.0
                            try:
                                v = float(str(r.get("Concentration_result_in_f_ml", "0")).replace("<", "").replace("Not specified", "0") or "0")
                                r["Flag_High_Concentration"] = v > HIGH_CONC_THRESHOLD
                            except:
                                r["Flag_High_Concentration"] = False
                            
                            # Auto-detect personal samples and mark as removed
                            pump_loc = str(r.get("Pump_Location", "") or "").lower()
                            _personal_keywords = ["personal", "personnel", "personeel", "personale", "individuel"]
                            if any(kw in pump_loc for kw in _personal_keywords):
                                r["row_status"] = "removed"
                                r["removal_reason"] = "Personal sample"
                            else:
                                r["row_status"] = "active"
                                r["removal_reason"] = None

                        if records:
                            df = pd.DataFrame(records)
                            df.insert(0, "Include", True)
                            df.insert(1, "Personal", False)
                            st.session_state.pdf_results[uf.name] = df
                            from utils.db_utils import check_duplicates
                            dupes = check_duplicates(df, site_info["Code"])
                            if dupes:
                                st.session_state.duplicates_info[uf.name] = dupes
                                st.write(f"  ↳ ⚠️ {len(dupes)} duplicate(s)")
                    except Exception as e:
                        st.error(f"  ✗ Parsing failed: {e}")
                        continue

                if st.session_state.pdf_results:
                    st.session_state.processing_done = True
                    total = sum(len(d) for d in st.session_state.pdf_results.values())
                    _auto_removed = sum(
                        int((d.get("row_status", pd.Series()) == "removed").sum())
                        for d in st.session_state.pdf_results.values()
                        if "row_status" in d.columns
                    ) if any("row_status" in d.columns for d in st.session_state.pdf_results.values()) else 0
                    _active_count = total - _auto_removed
                    _count_detail = f"{_active_count} active" + (f", {_auto_removed} auto-excluded" if _auto_removed else "")
                    if _skipped_files:
                        status.update(label=f"  Done — {total} samples ({_count_detail}) from {len(st.session_state.pdf_results)} file(s). {len(_skipped_files)} skipped (already uploaded).", state="complete")
                    else:
                        status.update(label=f"  Done — {total} samples ({_count_detail}) from {len(st.session_state.pdf_results)} file(s)", state="complete")
                elif _skipped_files:
                    status.update(label=f"  All {len(_skipped_files)} file(s) already uploaded for this site — nothing to process.", state="complete")
                else:
                    status.update(label="No samples extracted.", state="error")

        # ──────────────────────────────────────────────
        # REVIEW TABS
        # ──────────────────────────────────────────────
        if st.session_state.processing_done and st.session_state.pdf_results:
            st.markdown("---")
            st.markdown(
                '<div class="step-indicator"><div class="step-number">4</div><div class="step-text">Review extracted data & save</div></div>',
                unsafe_allow_html=True
            )

            tab_names = list(st.session_state.pdf_results.keys())
            saved_count = len(st.session_state.saved_files)
            if saved_count > 0:
                st.progress((len(st.session_state.saved_files) + len(st.session_state.skipped_files)) / len(tab_names), text=f"{len(st.session_state.saved_files)} saved, {len(st.session_state.skipped_files)} skipped / {len(tab_names)} total")

            for filename in tab_names:
                icon = "✅" if filename in st.session_state.saved_files else "⏭️" if filename in st.session_state.skipped_files else "📄"
                # Auto-expand only the first unsaved/unskipped file
                is_pending = filename not in st.session_state.saved_files and filename not in st.session_state.skipped_files
                first_pending = next((f for f in tab_names if f not in st.session_state.saved_files and f not in st.session_state.skipped_files), None)
                with st.expander(f"{icon} {filename}", expanded=(filename == first_pending)):
                    if filename in st.session_state.saved_files:
                        st.markdown(
                            '<div class="save-summary"><b>✓ Saved to database</b></div>',
                            unsafe_allow_html=True
                        )
                        continue
                    if filename in st.session_state.skipped_files:
                        st.markdown(
                            '<div class="save-summary" style="background:linear-gradient(135deg,#f8f9fa,#e9ecef);"><b>⏭️ Skipped</b></div>',
                            unsafe_allow_html=True
                        )
                        continue

                    df = st.session_state.pdf_results[filename]
                    dupes = st.session_state.duplicates_info.get(filename, {})

                    # Side-by-side: PDF | Data
                    pdf_col, data_col = st.columns([2, 3])

                    with pdf_col:
                        pdf_data = st.session_state.pdf_bytes.get(filename)
                        if pdf_data:
                            render_pdf_preview(pdf_data, height=520)
                        else:
                            st.info("PDF preview not available")

                    with data_col:
                        # Duplicates
                        if dupes:
                            st.markdown(f"⚠️ **{len(dupes)} potential duplicate(s)**", unsafe_allow_html=False)
                            with st.container():
                                for idx, info in dupes.items():
                                    if idx < len(df):
                                        sample = df.iloc[idx].get("Sample_no", "?")
                                        st.markdown(
                                            f'<div class="dup-box">'
                                            f'<b>Row {idx+1}</b> (Sample: {sample}) → '
                                            f'<span class="dup-existing">Exists in: {info["existing_doc"]} '
                                            f'({info["existing_date"]})</span></div>',
                                            unsafe_allow_html=True
                                        )

                        # High concentration
                        if "Flag_High_Concentration" in df.columns:
                            high = df[(df["Include"] == True) & (_to_bool(df["Flag_High_Concentration"]))]
                            if not high.empty:
                                st.markdown(
                                    f'<div class="metric-highlight">⚠️ <b>{len(high)}</b> sample(s) with concentration &gt; {HIGH_CONC_THRESHOLD} f/ml</div>',
                                    unsafe_allow_html=True
                                )
                                st.markdown("")

                        # Table
                        display_cols = [c for c in df.columns if c not in ("row_status", "upload_batch_id", "uploaded_by")]
                        edited = st.data_editor(
                            df[display_cols],
                            use_container_width=True,
                            hide_index=True,
                            key=f"ed_{filename}",
                            column_config={
                                "Include": st.column_config.CheckboxColumn("✓", default=True, width="small"),
                                "Personal": st.column_config.CheckboxColumn("👤", default=False, width="small", help="Mark as personal sample (saved but hidden from active view)"),
                                "🔁": st.column_config.TextColumn("🔁", width="small", disabled=True, help="⚠️ = duplicate exists in DB"),
                                "Duplicate_of": st.column_config.TextColumn("Duplicate of", width="medium", disabled=True, help="Existing PDF name and upload date"),
                                "Flag_High_Concentration": st.column_config.CheckboxColumn("⚠️ High", width="small", help=f"Concentration > {HIGH_CONC_THRESHOLD} f/ml"),
                                "Flag_EM_Concentration": st.column_config.NumberColumn("EM", format="%.0f", width="small"),
                                "Sample_no": st.column_config.TextColumn("Sample #", width="small"),
                                "Concentration_result": st.column_config.TextColumn("Conc."),
                                "Concentration_unit": st.column_config.TextColumn("Unit", width="small"),
                                "Concentration_result_in_f_ml": st.column_config.TextColumn("f/ml", width="small"),
                            },
                            column_order=["Include", "Personal", "🔁", "Sample_no", "Sample_Date", "Analysis_method",
                                          "Followed_Norm", "Volume", "Concentration_result",
                                          "Concentration_unit", "Concentration_result_in_f_ml",
                                          "Flag_High_Concentration", "Flag_EM_Concentration",
                                          "Lab_name", "Project_Name", "Building", "Pump_Location",
                                          "Report_number", "Duplicate_of", "Document_name",
                                          "Site_name", "Code", "Site_Address", "upload_date", "PDF_URL"],
                        )

                        # Actions
                        included = int(edited["Include"].sum()) if "Include" in edited.columns else len(edited)
                        excluded = len(edited) - included

                        c1, c2, c3 = st.columns([3, 1.2, 0.8])
                        with c1:
                            parts = [f"<b>{included}</b> to save"]
                            if excluded: parts.append(f"<span style='color:var(--text-muted)'>{excluded} excluded</span>")
                            st.markdown(f"<span style='font-size:0.85rem;'>{' · '.join(parts)}</span>", unsafe_allow_html=True)
                        with c2:
                            if st.button("💾 Save to DB", key=f"sv_{filename}", type="primary", use_container_width=True):
                                try:
                                    from utils.db_utils import write_to_output_table, log_upload
                                    drop_cols = [c for c in ["Include", "Personal", "🔁", "Duplicate_of"] if c in edited.columns]
                                    save_df = edited[edited["Include"] == True].drop(columns=drop_cols).copy()
                                    # Restore row_status from original df (excluded from data editor display)
                                    save_df["row_status"] = df.loc[save_df.index, "row_status"] if "row_status" in df.columns else "active"
                                    save_df["removal_reason"] = df.loc[save_df.index, "removal_reason"] if "removal_reason" in df.columns else None
                                    save_df["status_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                                    # Mark duplicates as removed, keep personal detection from earlier
                                    # Mark personal samples
                                    if "Personal" in edited.columns:
                                        personal_mask = edited.loc[save_df.index, "Personal"].fillna(False).astype(bool)
                                        for idx in save_df.index:
                                            if personal_mask.get(idx, False):
                                                save_df.loc[idx, "row_status"] = "removed"
                                                save_df.loc[idx, "removal_reason"] = "Personal sample"
                                            elif idx in dupes and save_df.loc[idx, "row_status"] != "removed":
                                                save_df.loc[idx, "row_status"] = "removed"
                                                save_df.loc[idx, "removal_reason"] = "Duplicate"
                                            elif save_df.loc[idx, "row_status"] != "removed":
                                                save_df.loc[idx, "row_status"] = "active"
                                    else:
                                        for idx in save_df.index:
                                            if idx in dupes and save_df.loc[idx, "row_status"] != "removed":
                                                save_df.loc[idx, "row_status"] = "removed"
                                                save_df.loc[idx, "removal_reason"] = "Duplicate"
                                            elif save_df.loc[idx, "row_status"] != "removed":
                                                save_df.loc[idx, "row_status"] = "active"
                                    write_to_output_table(save_df, uploaded_by=user, batch_id=st.session_state.batch_id)
                                    log_upload(
                                        filename=filename, site_code=site_info.get("Code", ""),
                                        site_name=site_info.get("Site_name", ""), uploaded_by=user,
                                        num_records=len(df), num_duplicates=len(dupes), num_saved=len(save_df),
                                        batch_id=st.session_state.batch_id,
                                        volume_path=st.session_state.volume_paths.get(filename, ""),
                                    )
                                    st.session_state.saved_files.add(filename)
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"Save failed: {e}")
                        with c3:
                            if st.button("Skip", key=f"skip_{filename}", use_container_width=True):
                                st.session_state.skipped_files.add(filename)
                                st.rerun()

            # All done
            if st.session_state.saved_files | st.session_state.skipped_files == set(tab_names):
                st.markdown("---")
                _n_saved = len(st.session_state.saved_files)
                _n_skipped = len(st.session_state.skipped_files)
                if _n_saved > 0 and _n_skipped > 0:
                    st.markdown(f'<div class="save-summary">🎉 <b>Done!</b> {_n_saved} saved, {_n_skipped} skipped. Navigate to Output Browser to manage records.</div>', unsafe_allow_html=True)
                elif _n_saved > 0:
                    st.markdown('<div class="save-summary">🎉 <b>All files saved!</b> Navigate to Output Browser to manage records.</div>', unsafe_allow_html=True)
                else:
                    st.markdown('<div class="save-summary">⏭️ <b>All files skipped.</b> No records were saved.</div>', unsafe_allow_html=True)
                st.markdown("")
                if st.button("📤 Process More Reports", use_container_width=True):
                    for k in ("pdf_results", "processing_done", "saved_files", "skipped_files", "duplicates_info", "pdf_bytes"):
                        st.session_state[k] = type(st.session_state[k])()
                    st.rerun()


    # ════════════════════════════════════════════════════════════
    # PAGE 2: OUTPUT BROWSER
    # ════════════════════════════════════════════════════════════

with tab_browser:

        st.markdown(
            '<div class="hero-section">'
            '<h2>Output Browser</h2>'
            '<p>Browse, edit, and manage all air monitoring results</p>'
            '</div>',
            unsafe_allow_html=True
        )

        from utils.db_utils import execute_query

        # Filters in a card

        sites_df = get_sites_for_user(user)
        if not sites_df.empty:
            sites_df = sites_df.sort_values("site_code").reset_index(drop=True)
            sites_df["display"] = sites_df["site_code"].fillna("") + " — " + sites_df["site_name"]
            site_options = ["All"] + sites_df["display"].tolist()
        else:
            site_options = ["All"]

        c1, c2, c3 = st.columns(3)
        with c1:
            f_site_display = st.selectbox("Site", site_options)
        with c2:
            f_status = st.multiselect("Status", ["active", "modified", "removed"], default=["active", "modified"])
        with c3:
            f_method = st.selectbox("Analysis", ["All", "Optical Microscopy", "Electron Microscopy", "Not specified"])

        dc1, dc2, dc3, dc4 = st.columns([1, 1, 1, 1])
        with dc1:
            f_date_col = st.selectbox("Date type", ["Sample Date", "Upload Date"], index=0,
                help="Sample Date = when the air sample was taken. Upload Date = when the PDF was uploaded to this tool.")
        with dc2:
            f_date_from = st.date_input("From", value=None)
        with dc3:
            f_date_to = st.date_input("To", value=None)
        with dc4:
            f_conc_min = st.number_input("Conc. ≥ (f/ml)", value=None, min_value=0.0, step=0.001, format="%.4f")
        _nac1, _nac2, _nac3, _nac4 = st.columns(4)
        with _nac1:
            f_na_sample_date = st.checkbox("Unknown Sample Date only", key="na_sample_date",
                help="Show only rows where Sample Date is blank or 'Not specified'")
        with _nac2:
            f_na_analysis = st.checkbox("Unknown Analysis Method only", key="na_analysis",
                help="Show only rows where Analysis Method is blank or 'Not specified'")
        with _nac3:
            f_na_concentration = st.checkbox("Unknown Concentration only", key="na_concentration",
                help="Show only rows where Concentration is blank or 'Not specified'")
        with _nac4:
            f_na_sample_no = st.checkbox("Unknown Sample No only", key="na_sample_no",
                help="Show only rows where Sample_no is blank or 'Not specified'")

        load_btn = st.button("🔍 Load Data", type="primary")
        # Resolve site
        f_site = "All"
        if f_site_display != "All" and not sites_df.empty:
            site_match = sites_df[sites_df["display"] == f_site_display]
            if not site_match.empty:
                f_site = site_match.iloc[0]["site_name"]

        conds = []
        if f_site != "All": conds.append(f"Site_name = '{f_site}'")
        if f_status and len(f_status) < 3:
            status_list = ", ".join([f"'{s}'" for s in f_status])
            conds.append(f"row_status IN ({status_list})")
        if not f_na_analysis:
            if f_method == "Not specified":
                conds.append("(Analysis_method IS NULL OR Analysis_method = '' OR LOWER(COALESCE(Analysis_method,'')) IN ('not specified', 'n/a', 'na', 'none', 'not available'))")
            elif f_method != "All":
                conds.append(f"Analysis_method = '{f_method}'")

        _date_col = "Sample_Date" if f_date_col == "Sample Date" else "upload_date"
        if f_date_from: conds.append(f"{_date_col} >= '{f_date_from}'")
        if f_date_to: conds.append(f"{_date_col} <= '{f_date_to} 23:59:59'")
        if f_na_sample_date:
            conds.append("(Sample_Date IS NULL OR Sample_Date = '' OR LOWER(COALESCE(Sample_Date,'')) IN ('not specified', 'n/a', 'na', 'none', 'not available'))")
        if f_na_analysis:
            conds.append("(Analysis_method IS NULL OR Analysis_method = '' OR LOWER(COALESCE(Analysis_method,'')) IN ('not specified', 'n/a', 'na', 'none', 'not available'))")
        if f_na_concentration:
            conds.append("(Concentration_result_in_f_ml IS NULL OR Concentration_result_in_f_ml = '' OR LOWER(COALESCE(Concentration_result_in_f_ml,'')) IN ('not specified', 'n/a', 'na', 'none', 'not available'))")
        if f_na_sample_no:
            conds.append("(Sample_no IS NULL OR Sample_no = '' OR LOWER(COALESCE(Sample_no,'')) IN ('not specified', 'n/a', 'na', 'none', 'not available'))")
        if f_conc_min is not None: conds.append(f"CAST(Concentration_result_in_f_ml AS DOUBLE) >= {f_conc_min}")
        where = " AND ".join(conds) if conds else "1=1"

        # Enforce user-level site access
        _allowed_codes = get_allowed_site_codes(user)
        if _allowed_codes:
            _codes_sql = ", ".join([f"'{c}'" for c in _allowed_codes])
            where = f"({where}) AND Code IN ({_codes_sql})"
        else:
            where = "1=0"  # No access = no data

        if load_btn:
            try:
                df = execute_query(f"SELECT * FROM {OUTPUT_TABLE} WHERE {where} ORDER BY upload_date DESC")
                if df is not None and not df.empty:
                    st.session_state["browser_data"] = df.copy()
                    st.session_state["browser_original"] = df.copy()
                else:
                    st.session_state["browser_data"] = None
                    st.info("No records match the filters.")
            except Exception as e:
                st.error(f"Query failed: {e}")

        if "browser_data" in st.session_state and st.session_state["browser_data"] is not None:
            df = st.session_state["browser_data"]
            st.markdown("")

            # Metrics
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Total Records", f"{len(df):,}")
            m2.metric("Unique Sites", df["Site_name"].nunique() if "Site_name" in df.columns else 0)
            m3.metric("Documents", df["Document_name"].nunique() if "Document_name" in df.columns else 0)
            high_count = int(_to_bool(df["Flag_High_Concentration"]).sum()) if "Flag_High_Concentration" in df.columns else 0
            with m4:
                st.metric(f"High Concentration (>{HIGH_CONC_THRESHOLD} f/ml)", high_count)
                if high_count > 0:
                    _hc_active = st.session_state.get("_browser_filter_high_conc", False)
                    if st.button(
                        "✕ Clear filter" if _hc_active else "🔍 Show only",
                        key="btn_filter_high_conc",
                        use_container_width=True,
                    ):
                        st.session_state["_browser_filter_high_conc"] = not _hc_active
                        st.rerun()

            # Apply high-conc filter if active
            if st.session_state.get("_browser_filter_high_conc", False) and "Flag_High_Concentration" in df.columns:
                df = df[_to_bool(df["Flag_High_Concentration"])].copy()
                st.info(f"🔍 Filtered: showing {len(df)} high concentration record(s). Click \"✕ Clear filter\" above to reset.")

            st.markdown("---")

            # Parse Sample_Date — stored as DD-Mon-YYYY (e.g. 20-Jan-2026)
            if "Sample_Date" in df.columns:
                def _parse_sample_date(s):
                    if pd.isna(s) or str(s).strip() in ('', 'None', 'NaT', 'Not specified', 'N/A', 'n/a', 'NA'):
                        return pd.NaT
                    for fmt in ('%d-%b-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d.%m.%Y'):
                        try:
                            return pd.to_datetime(s, format=fmt)
                        except Exception:
                            pass
                    return pd.to_datetime(s, errors='coerce')
                df["Sample_Date"] = df["Sample_Date"].apply(_parse_sample_date)

            # Parse upload_date to date-only (remove time portion)
            if "upload_date" in df.columns:
                df["upload_date"] = pd.to_datetime(df["upload_date"], errors="coerce").dt.date
                df["upload_date"] = pd.to_datetime(df["upload_date"], errors="coerce")

                # Sync browser_original to same date formats (prevents false "modified" detection)
                if "browser_original" in st.session_state and st.session_state["browser_original"] is not None:
                    _orig = st.session_state["browser_original"]
                    if "Sample_Date" in _orig.columns and _orig["Sample_Date"].dtype == "object":
                        _orig["Sample_Date"] = _orig["Sample_Date"].apply(_parse_sample_date)
                    if "upload_date" in _orig.columns:
                        _orig["upload_date"] = pd.to_datetime(_orig["upload_date"], errors="coerce").dt.date
                        _orig["upload_date"] = pd.to_datetime(_orig["upload_date"], errors="coerce")

            # Editable table
            edited = st.data_editor(
                df,
                use_container_width=True,
                hide_index=True,
                num_rows="fixed",
                key="browser_editor",
                column_config={
                    "row_id": st.column_config.TextColumn("ID", width="small", disabled=True),
                    "row_status": st.column_config.SelectboxColumn(
                        "Record Status", options=["active", "modified", "removed"], width="small",
                        help="active = live record · modified = edited after upload · removed = excluded from reporting"
                    ),
                    "removal_reason": st.column_config.TextColumn("Removal Reason", width="medium"),
                    "Sample_Date": st.column_config.DateColumn("Sample Date", format="YYYY-MM-DD"),
                    "upload_date": st.column_config.DateColumn("Upload Date", format="YYYY-MM-DD", disabled=True),
                    "Flag_High_Concentration": st.column_config.CheckboxColumn("⚠️ High", width="small", help=f"Concentration > {HIGH_CONC_THRESHOLD} f/ml"),
                    "Flag_EM_Concentration": st.column_config.NumberColumn("EM", format="%.0f", width="small"),
                    "PDF_URL": None,  # Hidden — use PDF Preview section below
                    "Delete_docs": None,  # Legacy V1 column — use row_status='removed' instead
                    "Frozen_Docs": None,  # Legacy V1 column
                    "upload_batch_id": None,  # Internal tracking
                    "uploaded_by": st.column_config.TextColumn("Uploaded By", disabled=True, width="small"),
                    "modified_by": st.column_config.TextColumn("Modified By", disabled=True, width="small"),
                    "status_updated_at": st.column_config.DatetimeColumn("Modified At", format="DD/MM/YYYY HH:mm", disabled=True, width="small"),
                },
                column_order=["row_status", "Site_name", "Code", "Site_Address", "upload_date",
                              "Document_name", "Report_number", "Sample_no",
                              "Sample_Date", "Analysis_method", "Followed_Norm", "Volume",
                              "Concentration_result", "Concentration_unit", "Concentration_result_in_f_ml",
                              "Lab_name", "Project_Name", "Building", "Pump_Location",
                              "Flag_EM_Concentration", "Flag_High_Concentration",
                              "uploaded_by", "modified_by", "status_updated_at", "row_id", "removal_reason"],
            )

            # Changes — compare only user-editable columns
            original = st.session_state.get("browser_original", df)
            try:
                _skip_cols = {"status_updated_at", "modified_by", "uploaded_by", "upload_date", "upload_batch_id",
                              "PDF_URL", "Delete_docs", "Frozen_Docs"}
                _compare_cols = [c for c in edited.columns if c in original.columns and c not in _skip_cols]
                _edited_cmp = edited[_compare_cols].fillna("").astype(str)
                _orig_cmp = original.loc[edited.index, _compare_cols].fillna("").astype(str)
                changes_mask = (_edited_cmp.values != _orig_cmp.values).any(axis=1)
                n_changes = int(changes_mask.sum())
            except:
                n_changes = 0

            st.markdown("---")
            c1, c2, c3 = st.columns([2.5, 1.2, 1])

            with c1:
                if n_changes > 0:
                    st.markdown(
                        f'<div class="metric-highlight">📝 <b>{n_changes}</b> row(s) modified — confirm to save</div>',
                        unsafe_allow_html=True
                    )
                else:
                    st.caption("No pending changes.")

            with c2:
                if st.button("✅ Confirm Changes", disabled=(n_changes == 0), type="primary", use_container_width=True):
                    if "row_id" not in edited.columns or edited[changes_mask]["row_id"].isna().any():
                        st.error("Cannot update rows without row_id.")
                    else:
                        try:
                            from utils.db_utils import update_rows
                            import time
                            changed = edited[changes_mask].copy()
                            changed["status_updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            for idx in changed.index:
                                orig_status = original.loc[idx, "row_status"] if idx in original.index else "active"
                                new_status = changed.loc[idx, "row_status"]
                                if new_status == "removed" and orig_status != "removed":
                                    # User manually removed — set reason
                                    changed.loc[idx, "removal_reason"] = "Deleted"
                                elif new_status in ("active", "modified") and orig_status == "removed":
                                    # User restored a removed row — clear reason
                                    changed.loc[idx, "removal_reason"] = None
                                    changed.loc[idx, "row_status"] = "active"
                                elif new_status in ("active", None) and orig_status in ("active", "modified"):
                                    # Data fields changed → mark as modified
                                    changed.loc[idx, "row_status"] = "modified"
                            # Retry up to 3 times on Delta concurrency conflicts
                            _max_retries = 3
                            for _attempt in range(1, _max_retries + 1):
                                try:
                                    update_rows(changed, modified_by=user)
                                    break  # Success
                                except Exception as _ue:
                                    if "DELTA_CONCURRENT" in str(_ue) and _attempt < _max_retries:
                                        time.sleep(2 * _attempt)  # Backoff: 2s, 4s
                                        continue
                                    raise _ue
                            st.success(f"✓ {n_changes} row(s) saved")
                            st.session_state["browser_data"] = edited.copy()
                            st.session_state["browser_original"] = edited.copy()
                        except Exception as e:
                            st.error(f"Update failed: {e}")

            with c3:
                import io
                buffer = io.BytesIO()
                df_xl = edited.copy()
                for col in df_xl.select_dtypes(include=["datetimetz"]).columns:
                    df_xl[col] = df_xl[col].dt.tz_localize(None)
                with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                    df_xl.to_excel(writer, index=False, sheet_name="Results")
                st.download_button(
                    "📥 Excel",
                    data=buffer.getvalue(),
                    file_name=f"air_monitoring_{datetime.now().strftime('%Y%m%d')}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )

            # ── PDF Preview ──
            st.markdown("---")
            st.markdown("##### 📄 PDF Preview")
            if "PDF_URL" in df.columns:
                pdf_files = df["PDF_URL"].dropna().unique().tolist()
                if pdf_files:
                    # Show document name instead of full path
                    doc_names = df[["Document_name", "PDF_URL"]].drop_duplicates("PDF_URL").dropna(subset=["PDF_URL"])
                    display_map = {row["PDF_URL"]: f"📄 {row['Document_name']}" for _, row in doc_names.iterrows()}
                    # ── Paste / type to find PDF ──
                    _pdf_paste = st.text_input(
                        "Paste or type filename",
                        value="",
                        key="pdf_paste_input",
                        placeholder="e.g. ITGA23-010259_report.pdf — partial names work",
                        help="Copy the Document_name from the table above and paste here to load its PDF directly."
                    )
                    _name_to_url = {
                        str(row["Document_name"]).lower(): row["PDF_URL"]
                        for _, row in doc_names.iterrows()
                    }
                    selected_pdf = None
                    if _pdf_paste.strip():
                        _search = _pdf_paste.strip().lower()
                        _found_name = None
                        for _doc_name, _url in _name_to_url.items():
                            if _search in _doc_name or _doc_name in _search:
                                selected_pdf = _url
                                _found_name = _doc_name
                                break
                        if selected_pdf:
                            st.caption(f"Found: 📄 {_found_name}")
                        else:
                            st.caption(f"No document matching '{_pdf_paste}' — try the dropdown below or reload with different filters.")
                    else:
                        selected_pdf = st.selectbox(
                            "Or select from dropdown",
                            options=[None] + pdf_files,
                            format_func=lambda x: "— select a document —" if x is None else display_map.get(x, x.split("/")[-1]),
                            key="pdf_preview_select"
                        )
                    if selected_pdf:
                        try:
                            # Convert SharePoint URL to Volume path if needed
                            _pdf_path = selected_pdf
                            if "sharepoint.com" in _pdf_path:
                                # Extract path after /General/ → maps to Volume
                                import urllib.parse
                                _decoded = urllib.parse.unquote(_pdf_path)
                                _parts = _decoded.split("/General/")
                                if len(_parts) > 1:
                                    _pdf_path = VOLUME_PATH + "/" + _parts[1]
                            # Read binary from Volume via SQL Warehouse
                            _safe_pdf_path = _pdf_path.replace("'", "''")  # Escape apostrophes for SQL
                            _pdf_query = f"SELECT content FROM read_files('{_safe_pdf_path}', format => 'binaryFile') LIMIT 1"
                            _pdf_result = execute_query(_pdf_query)
                            if _pdf_result is not None and not _pdf_result.empty:
                                pdf_bytes = _pdf_result.iloc[0]["content"]
                                if isinstance(pdf_bytes, str):
                                    pdf_bytes = bytes.fromhex(pdf_bytes)
                                render_pdf_preview(pdf_bytes, height=600)
                            else:
                                st.warning("Could not read PDF from volume.")
                        except Exception as e:
                            st.warning(f"Could not load PDF: {e}")
                else:
                    st.info("No PDF files linked to current records.")



            # ── High Concentration Samples (moved from Analytics) ──
            st.markdown("---")
            st.subheader("⚠️ High Concentration Samples")
            if "Flag_High_Concentration" in df.columns:
                high_df = df[_to_bool(df["Flag_High_Concentration"])]
                if not high_df.empty:
                    hc_display_cols = ["Site_name", "Code", "Document_name", "Sample_no", "Sample_Date",
                                       "Analysis_method", "Concentration_result", "Concentration_unit",
                                       "Concentration_result_in_f_ml", "Pump_Location"]
                    hc_avail = [c for c in hc_display_cols if c in high_df.columns]
                    st.dataframe(
                        high_df[hc_avail].sort_values("Concentration_result_in_f_ml", ascending=False).head(50),
                        use_container_width=True,
                        hide_index=True,
                    )
                    st.caption(f"Showing top 50 of {len(high_df)} high concentration samples (> {HIGH_CONC_THRESHOLD} f/ml)")
                else:
                    st.success("No high concentration samples in current filter.")


    # ════════════════════════════════════════════════════════════
    # PAGE 3: UPLOAD HISTORY
    # ════════════════════════════════════════════════════════════

with tab_history:

        st.markdown(
            '<div class="hero-section">'
            '<h2>Analytics</h2>'
            '<p>Air monitoring KPIs — site overview, data quality, concentration alerts</p>'
            '</div>',
            unsafe_allow_html=True
        )

        # ── Global Site Filter (affects all sections below) ──
        _user_sites = get_sites_for_user(user)
        if not _user_sites.empty:
            _site_filter_options = _user_sites[["site_code", "site_name"]].drop_duplicates().sort_values("site_code")
            _site_filter_labels = [f"{row['site_code']} — {row['site_name']}" for _, row in _site_filter_options.iterrows()]
            _analytics_site_filter = st.multiselect(
                "🔍 Filter by Site", _site_filter_labels, default=[],
                help="Leave empty to show all sites",
                placeholder="All sites",
                key="analytics_site_filter"
            )
            _filtered_site_codes = [s.split(" — ")[0] for s in _analytics_site_filter] if _analytics_site_filter else []
        else:
            _filtered_site_codes = []

        # ════════════════════════════════════════════════════════════
        # UPLOAD HISTORY
        # ════════════════════════════════════════════════════════════

        from utils.db_utils import get_upload_history
        history = get_upload_history(limit=10000)
        # Filter to user's allowed sites
        _allowed_codes = get_allowed_site_codes(user)
        if not history.empty and _allowed_codes and "site_code" in history.columns:
            history = history[history["site_code"].isin(_allowed_codes)]
        # Apply site filter
        if _filtered_site_codes and not history.empty and "site_code" in history.columns:
            history = history[history["site_code"].isin(_filtered_site_codes)]

        if history.empty:
            st.info("No uploads recorded yet. Process some PDFs to see history here.")
        else:
            m1, m2, m3 = st.columns(3)
            m1.metric("Total Uploads", f"{len(history):,}")
            m2.metric("Records Saved", f"{int(history['num_saved'].sum()):,}" if "num_saved" in history.columns else "0")
            m3.metric("Users", history["uploaded_by"].nunique() if "uploaded_by" in history.columns else 0)

            st.markdown("---")

            display_cols = ["upload_time", "filename", "site_name", "site_code",
                           "uploaded_by", "num_records", "num_duplicates_found", "num_saved", "status"]
            available_cols = [c for c in display_cols if c in history.columns]

            st.dataframe(
                history[available_cols],
                use_container_width=True,
                hide_index=True,
                column_config={
                    "upload_time": st.column_config.DatetimeColumn("When", format="DD/MM/YYYY HH:mm"),
                    "filename": st.column_config.TextColumn("File"),
                    "site_name": st.column_config.TextColumn("Site"),
                    "site_code": st.column_config.TextColumn("Code", width="small"),
                    "uploaded_by": st.column_config.TextColumn("User"),
                    "num_records": st.column_config.NumberColumn("Extracted", width="small"),
                    "num_duplicates_found": st.column_config.NumberColumn("Dupes", width="small"),
                    "num_saved": st.column_config.NumberColumn("Saved", width="small"),
                    "status": st.column_config.TextColumn("Status", width="small"),
                }
            )

            st.markdown("---")

            # ── Upload Activity Chart ──
            st.subheader("📅 Upload Activity")
            if "upload_time" in history.columns:
                try:
                    hist_copy = history.copy()
                    hist_copy["upload_time"] = pd.to_datetime(hist_copy["upload_time"])
                    hist_copy["upload_month"] = hist_copy["upload_time"].dt.to_period("M").astype(str)
                    monthly_uploads = hist_copy.groupby("upload_month").size().reset_index(name="Uploads")
                    monthly_uploads = monthly_uploads.tail(12)
                    st.bar_chart(monthly_uploads.set_index("upload_month"), y="Uploads", use_container_width=True)
                except:
                    st.info("Could not generate upload trend chart.")

        # ════════════════════════════════════════════════════════════
        # ANALYTICS — KPIs, Site Overview, Data Quality
        # ════════════════════════════════════════════════════════════

        from utils.db_utils import execute_query

        try:
            # Load all data for KPIs
            # Filter by user's allowed sites
            _allowed_codes = get_allowed_site_codes(user)
            if _allowed_codes:
                _codes_sql = ", ".join([f"'{c}'" for c in _allowed_codes])
                _analytics_where = f"Code IN ({_codes_sql})"
            else:
                _analytics_where = "1=0"
            all_data = execute_query(f"SELECT * FROM {OUTPUT_TABLE} WHERE {_analytics_where}")

            if all_data is not None and not all_data.empty:
                # ── Parse Sample_Date for year filtering ──
                if "Sample_Date" in all_data.columns:
                    def _parse_sd(s):
                        if pd.isna(s) or str(s).strip() in ('', 'None', 'NaT', 'Not specified', 'N/A', 'n/a', 'NA'):
                            return pd.NaT
                        for fmt in ('%d-%b-%Y', '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y'):
                            try:
                                return pd.to_datetime(s, format=fmt)
                            except Exception:
                                pass
                        return pd.to_datetime(s, errors='coerce')
                    all_data["_sample_date_parsed"] = all_data["Sample_Date"].apply(_parse_sd)
                    all_data["_sample_year"] = all_data["_sample_date_parsed"].dt.year.astype("Int64")
                else:
                    all_data["_sample_year"] = None

                # ── Year Filter ──
                available_years = sorted(all_data["_sample_year"].dropna().unique().tolist(), reverse=True)
                available_years_str = [str(int(y)) for y in available_years]
                selected_years = st.multiselect("Filter by Sampling Year", available_years_str, default=available_years_str,
                                                help="Select which sampling years to include in the analytics")
                selected_years_int = [int(y) for y in selected_years] if selected_years else available_years

                # ── Apply filters ──
                active = all_data[all_data["row_status"].isin(["active", "modified"])] if "row_status" in all_data.columns else all_data
                active = active[active["_sample_year"].isin(selected_years_int) | active["_sample_year"].isna()]
                if _filtered_site_codes:
                    active = active[active["Code"].isin(_filtered_site_codes)]
                total_records = len(active)
                total_sites = active["Code"].nunique() if "Code" in active.columns else 0
                total_docs = active["Document_name"].nunique() if "Document_name" in active.columns else 0
                high_conc = int(_to_bool(active["Flag_High_Concentration"]).sum()) if "Flag_High_Concentration" in active.columns else 0

                # ════════════════════════════════════════════════════════
                # CHIARA'S KPI DASHBOARD (3 categories)
                # ════════════════════════════════════════════════════════

                # Expected plants list (26 — from Chiara's Jul 2026 email)
                EXPECTED_PLANTS_2026 = [
                    "Aghires", "Athy", "Auneuil", "Branden", "Carpentras",
                    "Dabrowa", "Für", "Goor", "Gresik", "KOB", "Lagos",
                    "Maipú", "Manizales", "Mazan", "Meldreth", "Neubeckum",
                    "Novo Mesto", "Ottmarshein", "Rantigny", "Rennes",
                    "Roedding", "San Justo", "Santa Rosa", "Stirling",
                    "Tisselt", "Saint Loubes"
                ]

                # ── 1. DATA SHARING ──
                st.subheader("📊 Data Sharing")
                plants_expected = len(EXPECTED_PLANTS_2026)  # 26
                # Case-insensitive match: normalize both lists to lowercase
                _expected_lower = {p.lower() for p in EXPECTED_PLANTS_2026}
                _actual_sites_lower = set(active["Site_name"].dropna().str.lower().unique()) if "Site_name" in active.columns else set()
                _matched_sites = _expected_lower & _actual_sites_lower
                sites_sampled = len(_matched_sites)
                sharing_pct = (sites_sampled / plants_expected * 100) if plants_expected > 0 else 0

                ds1, ds2, ds3 = st.columns(3)
                ds1.metric("Plants Expected", plants_expected)
                ds2.metric("Sites Sampled", sites_sampled)
                ds3.metric("Data Sharing %", f"{sharing_pct:.1f}%")

                with st.expander("📋 Expected Plants List (26)", expanded=False):
                    _sampled_lower = set(active["Site_name"].dropna().str.lower().unique()) if "Site_name" in active.columns else set()
                    _plant_status = []
                    for p in sorted(EXPECTED_PLANTS_2026):
                        _status = "✅" if p.lower() in _sampled_lower else "⏳"
                        _plant_status.append(f"{_status} {p}")
                    # Display in 3 columns
                    _pc1, _pc2, _pc3 = st.columns(3)
                    _third = len(_plant_status) // 3 + 1
                    _pc1.markdown("\n".join(_plant_status[:_third]))
                    _pc2.markdown("\n".join(_plant_status[_third:2*_third]))
                    _pc3.markdown("\n".join(_plant_status[2*_third:]))

                st.markdown("---")

                # ── 2. COMPLIANCE ──
                st.subheader("✅ Compliance")
                total_samples = total_records

                # Filter for Electron Microscopy only for compliance
                em_mask = active["Analysis_method"] == "Electron Microscopy" if "Analysis_method" in active.columns else pd.Series([False] * len(active))
                em_data = active[em_mask]

                # Parse concentration for comparison
                def _safe_conc(val):
                    try:
                        s = str(val).replace("<", "").replace(",", ".").strip()
                        return float(s) if s and s not in ("", "None", "Not specified", "N/A") else 0.0
                    except (ValueError, TypeError):
                        return 0.0

                if "Concentration_result_in_f_ml" in em_data.columns:
                    em_conc = em_data["Concentration_result_in_f_ml"].apply(_safe_conc)
                else:
                    em_conc = pd.Series(dtype=float)

                above_01 = int((em_conc > 0.1).sum())
                above_001 = int((em_conc > 0.01).sum())
                compliance_01 = ((total_samples - above_01) / total_samples * 100) if total_samples > 0 else 100.0
                compliance_001 = ((total_samples - above_001) / total_samples * 100) if total_samples > 0 else 100.0

                c1, c2, c3, c4, c5 = st.columns(5)
                c1.metric("Total Samples", f"{total_samples:,}")
                c2.metric("EM > 0.01 f/ml", above_001, help="Electron Microscopy samples exceeding 0.01 f/ml")
                c3.metric("EM > 0.1 f/ml", above_01, help="Electron Microscopy samples exceeding 0.1 f/ml")
                c4.metric("Compliance (0.01)", f"{compliance_001:.1f}%")
                c5.metric("Compliance (0.1)", f"{compliance_01:.1f}%")

                st.markdown("---")

                # ── 3. AUTOMATION ──
                st.subheader("🤖 Automation")
                # Total parsed by AI = all records with row_status in (active, modified, removed)
                total_parsed = len(all_data) if all_data is not None else 0
                # Manual corrections = modified rows
                corrections = int((all_data["row_status"] == "modified").sum()) if "row_status" in all_data.columns else 0
                error_pct = (corrections / total_parsed * 100) if total_parsed > 0 else 0

                a1, a2, a3 = st.columns(3)
                a1.metric("Total Parsed by AI", f"{total_parsed:,}")
                a2.metric("Manual Corrections", corrections)
                a3.metric("Automation Error %", f"{error_pct:.2f}%")

                st.markdown("---")

                # ── Legacy metrics (quick summary) ──
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("Active Records", f"{total_records:,}")
                k2.metric("Active Sites", total_sites)
                k3.metric("Documents", total_docs)
                k4.metric(f"High Conc. (>{HIGH_CONC_THRESHOLD})", high_conc)

                st.markdown("---")

                # ── KPIs per Year ──
                st.subheader("📅 Samples per Year")
                if "_sample_year" in active.columns:
                    year_stats = active.groupby("_sample_year", dropna=False).agg(
                        Samples=("Code", "count"),
                        Sites=("Code", "nunique"),
                        Documents=("Document_name", "nunique"),
                        High_Conc=("Flag_High_Concentration", lambda x: int(_to_bool(x).sum())),
                        OM=("Analysis_method", lambda x: (x == "Optical Microscopy").sum()),
                        EM=("Analysis_method", lambda x: (x == "Electron Microscopy").sum()),
                    ).reset_index()
                    year_stats["_sample_year"] = year_stats["_sample_year"].astype("Int64").astype(str).replace("<NA>", "Unknown")
                    year_stats = year_stats.sort_values("_sample_year", ascending=False)
                    st.dataframe(
                        year_stats,
                        use_container_width=True,
                        hide_index=True,
                        column_config={
                            "_sample_year": st.column_config.TextColumn("Year", width="small"),
                            "Samples": st.column_config.NumberColumn("Samples", width="small"),
                            "Sites": st.column_config.NumberColumn("Sites", width="small"),
                            "Documents": st.column_config.NumberColumn("Docs", width="small"),
                            "High_Conc": st.column_config.NumberColumn("⚠️ High", width="small"),
                            "OM": st.column_config.NumberColumn("OM", width="small",
                                help="Optical Microscopy samples"),
                            "EM": st.column_config.NumberColumn("EM", width="small",
                                help="Electron Microscopy samples"),
                        }
                    )

                st.markdown("---")

                # ── Site Overview Table (like V1 Pipeline Overview) ──
                st.subheader("🏭 Site Overview")

                site_stats = active.groupby(["Code", "Site_name"]).agg(
                    Active_Samples=("Code", "count"),
                    Documents=("Document_name", "nunique"),
                    High_Conc=("Flag_High_Concentration", lambda x: int(_to_bool(x).sum())),
                    Latest_Upload=("upload_date", "max"),
                ).reset_index().sort_values("Active_Samples", ascending=False)

                st.dataframe(
                    site_stats,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Code": st.column_config.TextColumn("Code", width="small"),
                        "Site_name": st.column_config.TextColumn("Site"),
                        "Active_Samples": st.column_config.NumberColumn("Samples", width="small"),
                        "Documents": st.column_config.NumberColumn("Docs", width="small"),
                        "High_Conc": st.column_config.NumberColumn("⚠️ High", width="small"),
                        "Latest_Upload": st.column_config.DatetimeColumn("Last Upload", format="DD/MM/YYYY"),
                    }
                )

                st.markdown("---")

                # ── Row Status Summary (like V1 Removal Summary) ──
                col_left, col_right = st.columns(2)

                with col_left:
                    st.subheader("📋 Data Status Summary")
                    if "row_status" in all_data.columns:
                        status_counts = all_data["row_status"].value_counts().reset_index()
                        status_counts.columns = ["Status", "Count"]

                        # Color coding via HTML
                        status_html = ""
                        color_map = {"active": "#059669", "modified": "#d97706", "removed": "#dc2626"}
                        for _, row in status_counts.iterrows():
                            color = color_map.get(row["Status"], "#64748b")
                            pct = row["Count"] / len(all_data) * 100
                            status_html += (
                                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                                f'padding:10px 14px;margin:6px 0;border-radius:8px;border:1px solid #e2e8f0;">'
                                f'<div style="display:flex;align-items:center;gap:8px;">'
                                f'<div style="width:10px;height:10px;border-radius:50%;background:{color};"></div>'
                                f'<span style="font-weight:600;color:#1e293b;">{row["Status"]}</span></div>'
                                f'<div><span style="font-size:1.1rem;font-weight:700;color:#1e293b;">{row["Count"]:,}</span>'
                                f'<span style="color:#64748b;font-size:0.8rem;margin-left:6px;">({pct:.1f}%)</span></div>'
                                f'</div>'
                            )
                        st.markdown(status_html, unsafe_allow_html=True)

                        # Show removal_reason breakdown for removed records
                        if "removal_reason" in all_data.columns:
                            removed_data = all_data[all_data["row_status"] == "removed"].copy()
                            if not removed_data.empty:
                                # Normalize verbose reasons into clean categories
                                def _normalize_reason(r):
                                    if not r or r == "Unspecified":
                                        return "Unspecified"
                                    rl = str(r).lower()
                                    if "duplicate" in rl:
                                        return "Duplicate"
                                    if "personal" in rl:
                                        return "Personal sample"
                                    if "manually deleted" in rl or r == "Deleted":
                                        return "Deleted"
                                    return r
                                removed_data["_reason_clean"] = removed_data["removal_reason"].fillna("Unspecified").apply(_normalize_reason)
                                reason_counts = removed_data["_reason_clean"].value_counts().reset_index()
                                reason_counts.columns = ["Reason", "Count"]
                                reason_html = '<div style="margin-top:8px;padding-left:24px;">'
                                for _, rrow in reason_counts.iterrows():
                                    reason_html += (
                                        f'<div style="display:flex;justify-content:space-between;'
                                        f'padding:4px 10px;margin:3px 0;font-size:0.78rem;color:#64748b;">'
                                        f'<span>↳ {rrow["Reason"]}</span>'
                                        f'<span style="font-weight:600;">{rrow["Count"]:,}</span></div>'
                                    )
                                reason_html += '</div>'
                                st.markdown(reason_html, unsafe_allow_html=True)

                with col_right:
                    st.subheader("🔬 Analysis Method Breakdown")
                    if "Analysis_method" in active.columns:
                        method_counts = active["Analysis_method"].value_counts().reset_index()
                        method_counts.columns = ["Method", "Count"]

                        method_html = ""
                        method_colors = {"Optical Microscopy": "#2563eb", "Electron Microscopy": "#e8600a"}
                        for _, row in method_counts.iterrows():
                            color = method_colors.get(row["Method"], "#64748b")
                            pct = row["Count"] / len(active) * 100
                            method_html += (
                                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                                f'padding:10px 14px;margin:6px 0;border-radius:8px;border:1px solid #e2e8f0;">'
                                f'<div style="display:flex;align-items:center;gap:8px;">'
                                f'<div style="width:10px;height:10px;border-radius:50%;background:{color};"></div>'
                                f'<span style="font-weight:600;color:#1e293b;">{row["Method"]}</span></div>'
                                f'<div><span style="font-size:1.1rem;font-weight:700;color:#1e293b;">{row["Count"]:,}</span>'
                                f'<span style="color:#64748b;font-size:0.8rem;margin-left:6px;">({pct:.1f}%)</span></div>'
                                f'</div>'
                            )
                        st.markdown(method_html, unsafe_allow_html=True)



            else:
                st.info("No data available yet. Upload and process some PDFs first.")

        except Exception as e:
            st.error(f"Could not load analytics: {e}")


# ════════════════════════════════════════════════════════════
# PAGE 4: ADMIN
# ════════════════════════════════════════════════════════════

with tab_admin:

    st.markdown(
        '<div class="hero-section">'
        '<h2>Admin Panel</h2>'
        '<p>Manage site access — add or remove users per site</p>'
        '</div>',
        unsafe_allow_html=True
    )

    if not is_admin(user):
        st.warning("🔒 Admin access required. Contact your administrator if you need access.")
        st.stop()

    from utils.db_utils import execute_query, get_connection
    from utils.config import SITES_TABLE

    # Force-refresh sites cache when admin makes changes
    if st.button("🔄 Refresh Sites Cache", key="admin_refresh_cache"):
        load_all_sites.clear()
        st.success("Cache cleared — sites reloaded from database.")
        st.rerun()

    # Load all sites (bypass the user filter)
    try:
        all_sites_admin = spark.table(SITES_TABLE).toPandas() if 'spark' in dir() else execute_query(f"SELECT * FROM {SITES_TABLE} ORDER BY site_code")
    except Exception:
        all_sites_admin = execute_query(f"SELECT * FROM {SITES_TABLE} ORDER BY site_code")

    if all_sites_admin is None or all_sites_admin.empty:
        st.error("Could not load sites table.")
        st.stop()

    # Metrics
    total_sites = len(all_sites_admin)
    all_users_flat = set()
    site_code_to_users = {}  # Non-admin users only (admins have implicit access)
    _admin_emails_lower = {e.lower() for e in ADMIN_USERS}
    for _, row in all_sites_admin.iterrows():
        users_str = str(row.get("allowed_users", "") or "")
        users_list = [u.strip() for u in users_str.split("/") if u.strip()]
        # Filter out admin users from display (they have implicit access)
        non_admin_users = [u for u in users_list if u.lower() not in _admin_emails_lower]
        site_code_to_users[row["site_code"]] = non_admin_users
        all_users_flat.update([u.lower() for u in non_admin_users])

    mc1, mc2 = st.columns(2)
    mc1.metric("Total Sites", total_sites)
    mc2.metric("Total Users", len(all_users_flat))

    st.markdown("")
    st.markdown("##### 🏭 Sites & Access Management")
    st.caption("Manage user access per site. Click ➕ to add or ➖ to remove users.")

    # ── Site-by-site cards with inline actions ──
    for idx, row in all_sites_admin.iterrows():
        code = row["site_code"]
        name = row["site_name"]
        address = row.get("address", "") or ""
        current_users = site_code_to_users.get(code, [])
        user_count = len(current_users)

        with st.container(border=True):
            # Site header row with card-like styling
            site_col, badge_col, actions_col = st.columns([2, 0.5, 0.8])
            with site_col:
                _addr_part = f" · {address}" if address else ""
                st.markdown(
                    f'**{name}** &nbsp;&nbsp;<span style="font-size: 1rem; font-weight: 700; '
                    f'color: #e8600a; background: #fff7ed; padding: 2px 10px; border-radius: 6px; '
                    f'border: 1px solid #fed7aa;">{code}</span>',
                    unsafe_allow_html=True
                )
                if address:
                    st.caption(f"📍 {address}")

            with badge_col:
                st.markdown(
                    f'<div style="text-align: center; padding-top: 4px;">'
                    f'<span style="background: linear-gradient(135deg, #d1fae5, #ecfdf5); color: #065f46; '
                    f'padding: 4px 12px; border-radius: 20px; font-size: 0.75rem; font-weight: 700;">'
                    f'{user_count} user{"s" if user_count != 1 else ""}</span></div>',
                    unsafe_allow_html=True
                )

            with actions_col:
                btn_add_col, btn_remove_col = st.columns(2)
                with btn_add_col:
                    add_clicked = st.button("➕", key=f"add_btn_{code}", help=f"Add user to {name}", use_container_width=True)
                with btn_remove_col:
                    remove_clicked = st.button("➖", key=f"remove_btn_{code}", help=f"Remove user from {name}", use_container_width=True)

            # Show current user badges
            if current_users:
                badges_html = " ".join(
                    [f'<span style="display: inline-block; background: #fff7ed; color: #c2410c; '
                     f'border: 1px solid #fed7aa; padding: 3px 10px; border-radius: 20px; '
                     f'font-size: 0.72rem; font-weight: 600; margin: 3px 4px; '
                     f'letter-spacing: 0.3px;">{u.split("@")[0].upper()}</span>'
                     for u in sorted(current_users)]
                )
                st.markdown(f'<div style="padding: 4px 0 2px 0;">{badges_html}</div>', unsafe_allow_html=True)
            else:
                st.caption("No users assigned")

            # ── ADD USER FORM (inline, appears when ➕ clicked) ──
            if add_clicked:
                st.session_state[f"show_add_{code}"] = not st.session_state.get(f"show_add_{code}", False)
                st.session_state.pop(f"show_remove_{code}", None)

            if st.session_state.get(f"show_add_{code}", False):
                st.markdown("")
                add_col_input, add_col_btn = st.columns([3, 1])
                with add_col_input:
                    new_email = st.text_input(
                        "Email to add",
                        placeholder="user@etexgroup.com",
                        key=f"add_email_input_{code}",
                        label_visibility="collapsed"
                    )
                with add_col_btn:
                    confirm_add = st.button("✓ Add", type="primary", key=f"confirm_add_{code}", use_container_width=True)

                if confirm_add:
                    if not new_email or "@" not in new_email:
                        st.error("Enter a valid email.")
                    elif new_email.strip().lower() in [u.lower() for u in current_users]:
                        st.warning(f"`{new_email.strip()}` already has access.")
                    else:
                        email_clean = new_email.strip().lower()
                        new_users_list = current_users + [email_clean]
                        new_users_str = "/".join(new_users_list).replace("'", "''")
                        try:
                            conn = get_connection()
                            with conn.cursor() as cursor:
                                cursor.execute(f"""
                                    UPDATE {SITES_TABLE}
                                    SET allowed_users = '{new_users_str}'
                                    WHERE site_code = '{code}'
                                """)
                            conn.close()
                            load_all_sites.clear()
                            st.session_state[f"show_add_{code}"] = False
                            st.success(f"✅ Added `{email_clean}` to **{name}**")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")

            # ── REMOVE USER FORM (inline, appears when ➖ clicked) ──
            if remove_clicked:
                st.session_state[f"show_remove_{code}"] = not st.session_state.get(f"show_remove_{code}", False)
                st.session_state.pop(f"show_add_{code}", None)

            if st.session_state.get(f"show_remove_{code}", False):
                if not current_users:
                    st.info("No users to remove.")
                else:
                    st.markdown("")
                    rm_col_select, rm_col_btn = st.columns([3, 1])
                    with rm_col_select:
                        remove_email = st.selectbox(
                            "Select user",
                            options=sorted(current_users),
                            key=f"remove_select_{code}",
                            label_visibility="collapsed"
                        )
                    with rm_col_btn:
                        confirm_remove = st.button("✓ Remove", type="primary", key=f"confirm_remove_{code}", use_container_width=True)

                    if confirm_remove and remove_email:
                        new_users_list = [u for u in current_users if u.lower() != remove_email.lower()]
                        new_users_str = "/".join(new_users_list).replace("'", "''")
                        try:
                            conn = get_connection()
                            with conn.cursor() as cursor:
                                cursor.execute(f"""
                                    UPDATE {SITES_TABLE}
                                    SET allowed_users = '{new_users_str}'
                                    WHERE site_code = '{code}'
                                """)
                            conn.close()
                            load_all_sites.clear()
                            st.session_state[f"show_remove_{code}"] = False
                            st.success(f"✅ Removed `{remove_email}` from **{name}**")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed: {e}")

    # ── User Access Summary (collapsible) ──
    with st.expander("👤 User Access Summary", expanded=False):
        user_site_rows = []
        for _, row in all_sites_admin.iterrows():
            for email in str(row.get("allowed_users", "") or "").split("/"):
                e = email.strip()
                if e:
                    user_site_rows.append({"Email": e, "Site": row["site_name"], "Code": row["site_code"]})
        if user_site_rows:
            user_df = pd.DataFrame(user_site_rows)
            user_summary = user_df.groupby("Email")["Site"].apply(lambda x: ", ".join(sorted(x))).reset_index()
            user_summary.columns = ["Email", "Sites"]
            user_summary["#"] = user_df.groupby("Email").size().values
            st.dataframe(
                user_summary.sort_values("#", ascending=False),
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Email": st.column_config.TextColumn("Email"),
                    "#": st.column_config.NumberColumn("# Sites", width="small"),
                    "Sites": st.column_config.TextColumn("Sites"),
                },
            )
