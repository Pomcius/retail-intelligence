"""Streamlit-specific glue for the dashboard: cached data loading, global
filters, number formatting, and shared page chrome.

No analytical logic lives here — everything delegates to src.cleaning /
src.metrics / src.segmentation. This module only exists because Streamlit
caching (`st.cache_data`/`st.cache_resource`) and widget state are
Streamlit-specific concerns that don't belong in the reusable analytics
layer.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from src.database import DASHBOARD_DB_PATH, get_connection

# --------------------------------------------------------------------------
# Cached data loading
# --------------------------------------------------------------------------
def database_exists() -> bool:
    return DASHBOARD_DB_PATH.exists()


@st.cache_resource(show_spinner=False)
def _connection():
    return get_connection(DASHBOARD_DB_PATH, read_only=True)


@st.cache_data(show_spinner="Loading order data...")
def load_orders_analytics() -> pd.DataFrame:
    return _connection().execute("SELECT * FROM orders_analytics").fetchdf()


@st.cache_data(show_spinner="Loading item-level data...")
def load_order_items_analytics() -> pd.DataFrame:
    return _connection().execute("SELECT * FROM order_items_analytics").fetchdf()


def require_database() -> bool:
    """Stops page execution with a clear message if the DuckDB database
    is missing, instead of crashing with a raw exception."""
    if not database_exists():
        st.error(
            "**Dashboard database not found.**\n\n"
            "This dashboard reads from `data/dashboard.duckdb`, which is committed to the repo. "
            "If it is missing, restore it with `git checkout data/dashboard.duckdb`, or rebuild it:\n"
            "1. Place the Olist CSVs in `data/raw/` (see `data/raw/README.md`)\n"
            "2. `python -m src.database && python -m src.export_dashboard_db`"
        )
        st.stop()
    return True


# --------------------------------------------------------------------------
# Page chrome
# --------------------------------------------------------------------------
_BASE_CSS = """
<style>
.block-container { padding-top: 2.2rem; padding-bottom: 3rem; max-width: 1200px; }
[data-testid="stMetricValue"] { font-size: 1.65rem; }
[data-testid="stMetricLabel"] { font-size: 0.85rem; color: #6b6a66; }
hr { margin: 0.6rem 0 1.2rem 0; }
</style>
"""

METHODOLOGY_MD = """
**Revenue** — delivered-order product/item revenue only (`SUM(item_revenue)`); excludes freight and is never treated as profit (the dataset has no cost data).

**Customer** — identified by `customer_unique_id`, not `customer_id` (Olist assigns a new `customer_id` per order, even for the same person).

**Repeat customer** — a customer with 2+ delivered orders (lifetime, no time limit). Retention-window rates (30/60/90/180-day) are a separate, stricter figure that also adjusts for how long a customer has been observable.

**On-time delivery** — actual delivery date ≤ estimated delivery date, computed only for delivered orders with a known actual delivery date.

**Review metrics** — orders with no review are excluded from average score calculations, never scored as 0.

**Observed customer revenue** — revenue recorded within this ~2-year historical dataset only; not a lifetime-value projection.

**Segmentation** — behavior-based (not RFM — see Customer Intelligence page for why), using a 75th-percentile revenue threshold and a 90-day recency threshold, both documented in README.md.
"""


def apply_base_style() -> None:
    st.markdown(_BASE_CSS, unsafe_allow_html=True)


def render_methodology_expander() -> None:
    with st.sidebar.expander("Methodology & definitions"):
        st.markdown(METHODOLOGY_MD)


# --------------------------------------------------------------------------
# Global filters
# --------------------------------------------------------------------------
def render_sidebar_filters(orders_analytics: pd.DataFrame) -> pd.DataFrame:
    """Renders the shared date-range and state filters in the sidebar and
    returns the filtered orders_analytics. Widget keys are shared across
    pages so a filter choice persists as the user navigates."""
    st.sidebar.header("Filters")

    min_date = orders_analytics["order_purchase_timestamp"].min().date()
    max_date = orders_analytics["order_purchase_timestamp"].max().date()
    date_range = st.sidebar.date_input(
        "Purchase date range", value=(min_date, max_date),
        min_value=min_date, max_value=max_date, key="filter_date_range",
    )

    states = sorted(orders_analytics["customer_state"].dropna().unique())
    selected_states = st.sidebar.multiselect(
        "Customer state", options=states, default=[], key="filter_states",
        help="Leave empty to include all states.",
    )

    filtered = orders_analytics
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        purchase_date = filtered["order_purchase_timestamp"].dt.date
        filtered = filtered[(purchase_date >= start) & (purchase_date <= end)]
    if selected_states:
        filtered = filtered[filtered["customer_state"].isin(selected_states)]

    if len(filtered) < len(orders_analytics):
        st.sidebar.caption(f"Showing {len(filtered):,} of {len(orders_analytics):,} orders.")

    render_methodology_expander()
    return filtered


def apply_same_filters_to_items(order_items_analytics: pd.DataFrame) -> pd.DataFrame:
    """Applies the same date/state filters (from session_state, set by
    render_sidebar_filters) to the item-grain table, so category-level
    charts stay consistent with the order-grain KPIs on the same page."""
    filtered = order_items_analytics
    date_range = st.session_state.get("filter_date_range")
    if isinstance(date_range, tuple) and len(date_range) == 2:
        start, end = date_range
        purchase_date = filtered["order_purchase_timestamp"].dt.date
        filtered = filtered[(purchase_date >= start) & (purchase_date <= end)]
    selected_states = st.session_state.get("filter_states")
    if selected_states:
        filtered = filtered[filtered["customer_state"].isin(selected_states)]
    return filtered


# --------------------------------------------------------------------------
# Number formatting
# --------------------------------------------------------------------------
def format_currency_compact(value: float) -> str:
    if pd.isna(value):
        return "—"
    if abs(value) >= 1_000_000:
        return f"R$ {value / 1_000_000:.2f}M"
    if abs(value) >= 1_000:
        return f"R$ {value / 1_000:.1f}K"
    return f"R$ {value:,.2f}"


def format_currency(value: float) -> str:
    return "—" if pd.isna(value) else f"R$ {value:,.2f}"


def format_number(value: float) -> str:
    return "—" if pd.isna(value) else f"{value:,.0f}"


def format_percent(value: float, decimals: int = 1) -> str:
    return "—" if pd.isna(value) else f"{value * 100:.{decimals}f}%"
