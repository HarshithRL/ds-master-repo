from __future__ import annotations
 
import streamlit as st
 
def trigger_customer_search() -> None:
    st.session_state["customer_search_requested"] = True
 
# =============================================================================
# SIDEBAR
# =============================================================================
 
def render_sidebar(
    loaded_customer_id: str = "",
) -> tuple[str, bool]:
    """Render the sidebar and customer search"""
 
    # =========================================================================
    # SIDEBAR CSS
    # =========================================================================

    st.markdown(
        """
        <style>

        /* Refined search panel */
        section[data-testid="stSidebar"] [data-testid="stTextInput"] input {
            border-radius: 10px !important;
            min-height: 42px !important;
            box-shadow: 0 3px 12px rgba(10, 16, 40, .08);
        }
        section[data-testid="stSidebar"] [data-testid="stWidgetLabel"] {
            margin-bottom: .35rem;
        }

        /* =============================================================
        AXIOM SIDEBAR
        ============================================================= */

        section[data-testid="stSidebar"] {
            background:
                radial-gradient(
                    circle at 10% 82%,
                    rgba(111, 76, 255, 0.28) 0%,
                    rgba(111, 76, 255, 0.10) 24%,
                    transparent 48%
                ),
                linear-gradient(
                    180deg,
                    #202747 0%,
                    #252653 52%,
                    #29235C 100%
                ) !important;

            border-right: 1px solid rgba(255,255,255,0.06) !important;
            height: 100vh !important;
        }

        section[data-testid="stSidebar"] > div {
            background: transparent !important;
        }

        section[data-testid="stSidebar"]
        [data-testid="stSidebarContent"] {
            height: 100vh !important;
            background: transparent !important;
            overflow: hidden !important;
        }

        /* =============================================================
        AXIOM DECORATIVE SIDEBAR ACCENT
        ============================================================= */
        
        section[data-testid="stSidebar"] {
            position: relative !important;
            overflow: hidden !important;
        }
        
        /* Soft purple sweep at bottom */
        section[data-testid="stSidebar"]::before {
            content: "";
            position: absolute;
        
            left: -110px;
            bottom: -115px;
        
            width: 360px;
            height: 300px;
        
            background: linear-gradient(
                135deg,
                rgba(112, 76, 255, 0.00) 15%,
                rgba(112, 76, 255, 0.12) 48%,
                rgba(112, 76, 255, 0.38) 100%
            );
        
            border-radius: 50% 50% 0 0;
        
            transform: rotate(27deg);
        
            pointer-events: none;
            z-index: 0;
        }
        
        /* Smaller secondary sweep */
        section[data-testid="stSidebar"]::after {
            content: "";
            position: absolute;
        
            left: -150px;
            bottom: -175px;
        
            width: 390px;
            height: 310px;
        
            background: linear-gradient(
                135deg,
                transparent 30%,
                rgba(139, 104, 250, 0.18) 70%,
                rgba(99, 45, 250, 0.30) 100%
            );
        
            border-radius: 50% 50% 0 0;
        
            transform: rotate(42deg);
        
            pointer-events: none;
            z-index: 0;
        }
        
        /* Keep actual sidebar widgets above decoration */
        section[data-testid="stSidebar"]
        [data-testid="stSidebarContent"] {
            position: relative !important;
            z-index: 1 !important;
        }
        /* =============================================================
        SIDEBAR CONTENT
        ============================================================= */

        section[data-testid="stSidebar"] .block-container {
            box-sizing: border-box !important;
            width: 100% !important;
            max-width: none !important;
            height: 100vh !important;

            padding-top: 1.6rem !important;
            padding-left: 1.15rem !important;
            padding-right: 1.15rem !important;
            padding-bottom: 1rem !important;

            margin: 0 !important;
        }

        /* =============================================================
        CUSTOMER SEARCH TITLE
        ============================================================= */

        .sidebar-search-title {
            margin: 0 0 0.8rem 0;

            color: #B9B8D5;

            font-size: 0.67rem;
            line-height: 0.9rem;
            font-weight: 700;

            letter-spacing: 0.11em;
        }


        /* =============================================================
        FIELD LABEL
        ============================================================= */

        .sidebar-field-label {
            margin: 0 0 0.45rem 0;

            color: #F5F4FC;

            font-size: 0.80rem;
            line-height: 1rem;
            font-weight: 600;
        }

        section[data-testid="stSidebar"]
        [data-testid="stWidgetLabel"] p {
            color: #F5F4FC !important;
            font-size: 0.80rem !important;
            font-weight: 600 !important;
        }


        /* =============================================================
        SAP CUSTOMER ID INPUT
        ============================================================= */

        section[data-testid="stSidebar"]
        div[data-baseweb="base-input"] {
            background: rgba(255,255,255,0.075) !important;

            border: 1px solid rgba(189,174,255,0.28) !important;
            border-radius: 8px !important;

            overflow: hidden !important;
            box-shadow: none !important;

            transition:
                border-color 0.15s ease,
                background 0.15s ease,
                box-shadow 0.15s ease;
        }

        section[data-testid="stSidebar"]
        div[data-baseweb="base-input"]:hover {
            background: rgba(255,255,255,0.10) !important;
            border-color: rgba(189,174,255,0.55) !important;
        }

        section[data-testid="stSidebar"]
        div[data-baseweb="input"]:focus-within
        div[data-baseweb="base-input"] {
            background: rgba(255,255,255,0.11) !important;

            border-color: #8D6CFF !important;

            box-shadow:
                0 0 0 2px rgba(141,108,255,0.18) !important;
        }

        section[data-testid="stSidebar"] input {
            color: #1F2347 !important;
            -webkit-text-fill-color: #1F2347 !important;
            caret-color: #663BFF !important;
            background: transparent !important;
        }

        section[data-testid="stSidebar"] input::placeholder {
            color: #AAAAC3 !important;
            opacity: 1 !important;
        }


        /* =============================================================
        CUSTOMER FORM NAVIGATION
        ============================================================= */

        .sidebar-menu-spacing {
            height: 1.5rem;
        }

        .sidebar-customer-form {
            box-sizing: border-box;

            display: flex;
            align-items: center;

            width: 100%;
            min-height: 48px;

            gap: 10px;
            padding: 8px 10px;

            color: #FFFFFF;

            background: rgba(119,82,255,0.20);

            border-left: 3px solid #8B68FA;
            border-radius: 8px;
        }

        .sidebar-form-label {
            color: #FFFFFF;

            font-size: 14px;
            line-height: 20px;
            font-weight: 600;

            white-space: nowrap;
        }


        /* =============================================================
        AXIOM LOADING BAR
        ============================================================= */

        .axiom-loading-track {
            width: 100%;
            height: 3px;

            margin-top: 6px;

            overflow: hidden;
            border-radius: 999px;

            background: rgba(255,255,255,0.12);
        }

        .axiom-loading-bar {
            width: 35%;
            height: 100%;

            border-radius: 999px;

            background: #8B68FA;

            animation: axiom-loading 1s ease-in-out infinite;
        }

        @keyframes axiom-loading {
            0% {
                transform: translateX(-120%);
            }

            100% {
                transform: translateX(320%);
            }
        }


        /* =============================================================
        SIDEBAR COLLAPSE BUTTON
        ============================================================= */

        section[data-testid="stSidebar"]
        [data-testid="stSidebarCollapseButton"] {
            color: #C8C5DB !important;
        }

        section[data-testid="stSidebar"]
        [data-testid="stSidebarCollapseButton"] svg {
            fill: #C8C5DB !important;
        }

        </style>
        """,
        unsafe_allow_html=True,
    )

    # =========================================================================
    # SIDEBAR CONTENT
    # =========================================================================
 
    with st.sidebar:
                   
        # =====================================================================
        # CUSTOMER SEARCH
        # =====================================================================
 
        st.markdown(
            """
            <div class="sidebar-search-title">
                CUSTOMER SEARCH
            </div>
            """,
            unsafe_allow_html=True,
        )
 
        st.markdown(
            """
            <div class="sidebar-field-label">
                SAP Customer ID
            </div>
            """,
            unsafe_allow_html=True,
        )
 
        customer_id_input = st.text_input(
            "SAP Customer ID",
            value=loaded_customer_id,
            key="sidebar_customer_id",
            placeholder="Enter customer ID",
            label_visibility="collapsed",
            on_change=trigger_customer_search,
        )
 
        load_customer_clicked = st.session_state.pop(
            "customer_search_requested",
            False,
        )
 
    return customer_id_input, load_customer_clicked
