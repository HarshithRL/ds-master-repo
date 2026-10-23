"""
AXIOM app: the request portal for everyone and the Customer Master Workbench
page for the Master Data team. Neither page is in a menu; the portal header
shows a "Master Data" button to team members (portal/core/identity.py).
"""

import streamlit as st

pages = [
    st.Page("request_portal.py", title="AXIOM", default=True),
    st.Page("master_data_workbench.py", title="Master Data Workbench", url_path="workbench"),
]

st.navigation(pages, position="hidden").run()
