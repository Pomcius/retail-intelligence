"""Customer Intelligence — segmentation, retention, and cohort analysis.

Segments, retention windows, and cohorts describe a customer's complete
purchase history, so (unlike Executive Overview / Operations) this page
intentionally uses the full dataset rather than the sidebar date/state
filters — slicing mid-history would corrupt segment and cohort membership.
"""

import pandas as pd
import streamlit as st

from src import charts, dashboard
from src import metrics as m
from src import segmentation as seg

st.set_page_config(page_title="Customer Intelligence | Retail Intelligence", layout="wide")
dashboard.apply_base_style()
dashboard.require_database()

orders_analytics = dashboard.load_orders_analytics()
# Filters are still rendered for a consistent sidebar/methodology experience
# across pages, but intentionally not applied below — see module docstring.
dashboard.render_sidebar_filters(orders_analytics)

st.title("Customer Intelligence")
st.caption("Segmentation, retention, and cohorts — based on each customer's complete purchase history (not the sidebar filters).")

customer_summary = seg.build_customer_summary(orders_analytics)
segmented = seg.assign_customer_segment(customer_summary)

# --- Customer segment value --------------------------------------------
st.subheader("Customer Segment Value")
segment_summary = (
    segmented.groupby("segment")
    .agg(customers=("customer_unique_id", "count"), total_revenue=("total_revenue", "sum"),
         avg_revenue=("total_revenue", "mean"))
    .reset_index()
)
segment_summary["pct_of_customers"] = segment_summary["customers"] / segment_summary["customers"].sum() * 100
segment_summary["pct_of_revenue"] = segment_summary["total_revenue"] / segment_summary["total_revenue"].sum() * 100

col1, col2 = st.columns([3, 2])
with col1:
    st.plotly_chart(charts.segment_comparison_chart(segment_summary), width="stretch")
with col2:
    st.dataframe(
        segment_summary.sort_values("total_revenue", ascending=False)
        .assign(
            Customers=lambda d: d["customers"].map(dashboard.format_number),
            Revenue=lambda d: d["total_revenue"].map(dashboard.format_currency_compact),
            **{"% Revenue": lambda d: d["pct_of_revenue"].round(1).astype(str) + "%"},
        )[["segment", "Customers", "Revenue", "% Revenue"]]
        .rename(columns={"segment": "Segment"}),
        hide_index=True, width="stretch",
    )
top_segment = segment_summary.sort_values("pct_of_revenue", ascending=False).iloc[0]
st.caption(
    f"**{top_segment['segment']}** customers are only {top_segment['pct_of_customers']:.1f}% of customers but "
    f"{top_segment['pct_of_revenue']:.1f}% of observed revenue — count and economic contribution are very different things here. "
    "\"Observed revenue\" describes revenue within this dataset only, not a projected lifetime value."
)

with st.expander("Why not RFM (Recency, Frequency, Monetary) segmentation?"):
    st.markdown(
        "Traditional RFM was evaluated and rejected: **97.0% of customers placed exactly one delivered order**, "
        "leaving almost no variation to build a Frequency quintile from — it would mostly score noise. "
        "Recency (median 218 days) and Monetary value (highly skewed: mean R$141.62 vs. median R$89.73, "
        "top 10% of customers = 41.1% of revenue) do have real variation, so they're used directly instead, "
        "combined with a simple repeat/one-time behavioral split. Thresholds: 75th percentile of customer "
        "revenue = \"high value\"; 90 days since last purchase = \"recent\" (a business heuristic chosen for "
        "consistency with the retention-window analysis below, not a statistically optimized cutoff)."
    )

st.divider()

# --- Retention ------------------------------------------------------------
st.subheader("Retention")
retention_col1, retention_col2 = st.columns([1, 2])
with retention_col1:
    st.metric("Repeat Customer Rate (lifetime)", dashboard.format_percent(m.repeat_customer_rate(orders_analytics)))
    st.caption("No time limit — any customer with 2+ delivered orders, ever.")
with retention_col2:
    window_results = pd.DataFrame(
        [seg.retention_window_rate(orders_analytics, w) for w in [30, 60, 90, 180]]
    )
    st.plotly_chart(charts.retention_window_chart(window_results), width="stretch")
st.caption(
    "Retention-window rates only count customers who've had *at least* that many days since their first "
    "purchase to be observed returning — a customer who bought 20 days ago isn't counted against the 90-day rate. "
    "This is why these figures are lower than the lifetime repeat rate: most customers who ever return take "
    "several months to do so."
)

st.divider()

# --- Cohort retention -------------------------------------------------------
st.subheader("Cohort Retention")
matrix, cohort_sizes = seg.build_cohort_retention_matrix(orders_analytics)
display_matrix = matrix.loc[matrix.index >= "2017-01"]
st.plotly_chart(charts.cohort_heatmap(display_matrix), width="stretch")
st.caption(
    "Rows: month of first delivered purchase. Columns: months since then. Blank cells are calendar months "
    "that haven't happened yet for that cohort — never shown as 0%. Retention drops sharply after each "
    "cohort's first month (typically under 1%/month) with no clear trend across cohorts — low repeat "
    "purchasing looks structural here, not a recent decline."
)

st.divider()

# --- Frequency & value ------------------------------------------------------
col3, col4 = st.columns(2)
with col3:
    st.subheader("Purchase Frequency")
    st.plotly_chart(charts.frequency_distribution_chart(customer_summary), width="stretch")
    st.caption("97.0% of customers placed exactly one delivered order.")
with col4:
    st.subheader("Repeat vs. One-Time Value")
    is_repeat = customer_summary["delivered_order_count"] >= 2
    repeat_avg_rev = customer_summary.loc[is_repeat, "total_revenue"].mean()
    onetime_avg_rev = customer_summary.loc[~is_repeat, "total_revenue"].mean()
    repeat_aov = customer_summary.loc[is_repeat, "average_order_value"].mean()
    onetime_aov = customer_summary.loc[~is_repeat, "average_order_value"].mean()
    st.markdown(f"""
| | Observed revenue / customer | AOV / order |
|---|---|---|
| One-time | {dashboard.format_currency(onetime_avg_rev)} | {dashboard.format_currency(onetime_aov)} |
| Repeat | {dashboard.format_currency(repeat_avg_rev)} | {dashboard.format_currency(repeat_aov)} |
""")
    st.caption(
        f"Repeat customers generate ~{repeat_avg_rev / onetime_avg_rev:.1f}x the observed revenue of one-time "
        "customers — because they purchase more often, not because each order is larger (their per-order AOV "
        "is actually slightly lower)."
    )
