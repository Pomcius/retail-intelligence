"""Retail Intelligence — Streamlit entry point.

Run with: streamlit run app.py

This file is only the landing page and shared setup; each dashboard page
lives in pages/ and pulls its data/metrics from src/ (never recomputes
analysis inline). See README.md for the full methodology.
"""

import streamlit as st

from src import dashboard

st.set_page_config(page_title="Retail Intelligence", layout="wide")
dashboard.apply_base_style()

st.title("Retail Intelligence")
st.caption("E-commerce performance analysis of the Olist Brazilian marketplace dataset — ~96,500 delivered orders, 2016–2018.")

st.markdown(
    "This dashboard analyzes revenue, customer retention, and delivery operations to answer one question: "
    "**where are the biggest opportunities to improve customer experience, repeat purchasing, and revenue performance?**"
)

st.divider()

col1, col2 = st.columns(2)
with col1:
    st.page_link("pages/1_Executive_Overview.py", label="**Executive Overview**", icon=":material/dashboard:")
    st.caption("Headline KPIs, revenue trends, category and geographic performance.")
    st.page_link("pages/2_Customer_Intelligence.py", label="**Customer Intelligence**", icon=":material/group:")
    st.caption("Customer segmentation, retention windows, and cohort analysis.")
with col2:
    st.page_link("pages/3_Operations.py", label="**Operations**", icon=":material/local_shipping:")
    st.caption("Delivery performance and its relationship to customer reviews.")
    st.page_link("pages/4_Recommendations.py", label="**Recommendations**", icon=":material/lightbulb:")
    st.caption("Evidence-based findings and suggested next actions.")

st.divider()
dashboard.render_methodology_expander()

if not dashboard.database_exists():
    st.warning(
        "`data/dashboard.duckdb` is missing. Restore it with `git checkout data/dashboard.duckdb`, "
        "or rebuild it (see README, \"Running Locally\"), then reload this page."
    )
