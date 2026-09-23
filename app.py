"""Retail Intelligence — Streamlit entry point.

Run with: streamlit run app.py

Page content lives in pages/; this file only configures shared app settings
and a landing view. Individual dashboard pages are added in Phase 6.
"""

import streamlit as st

st.set_page_config(
    page_title="Retail Intelligence",
    page_icon=None,
    layout="wide",
)

st.title("Retail Intelligence")
st.caption(
    "Business intelligence for e-commerce: revenue, retention, operations, "
    "and customer experience, built on the Olist Brazilian e-commerce dataset."
)
st.info(
    "Dashboard pages are not built yet — this project is in the data "
    "exploration and cleaning phase. See README.md for progress."
)
