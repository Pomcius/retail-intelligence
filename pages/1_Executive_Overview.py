"""Executive Overview — headline KPIs and top-level business performance.

Answers: "How is the business performing overall?" All data/chart logic is
pulled from src/metrics.py, src/segmentation.py, and src/charts.py — this
file only wires filtered data into KPI cards and chart calls.
"""

import streamlit as st

from src import charts, dashboard
from src import metrics as m
from src import segmentation as seg

st.set_page_config(page_title="Executive Overview | Retail Intelligence", layout="wide")
dashboard.apply_base_style()
dashboard.require_database()

orders_analytics = dashboard.load_orders_analytics()
order_items_analytics = dashboard.load_order_items_analytics()

filtered_orders = dashboard.render_sidebar_filters(orders_analytics)
filtered_items = dashboard.apply_same_filters_to_items(order_items_analytics)

st.title("Executive Overview")
st.caption("E-commerce performance across revenue, customers, and delivery — delivered orders only.")

# --- Headline KPIs ----------------------------------------------------------
row1 = st.columns(4)
row1[0].metric("Revenue", dashboard.format_currency_compact(m.total_revenue(filtered_orders)))
row1[1].metric("Delivered Orders", dashboard.format_number(m.order_count(filtered_orders)))
row1[2].metric("Customers", dashboard.format_number(m.unique_customer_count(filtered_orders)))
row1[3].metric("Average Order Value", dashboard.format_currency(m.average_order_value(filtered_orders)))

row2 = st.columns(3)
row2[0].metric("Repeat Customer Rate", dashboard.format_percent(m.repeat_customer_rate(filtered_orders)))
row2[1].metric("On-Time Delivery", dashboard.format_percent(m.on_time_delivery_rate(filtered_orders)))
avg_review = m.average_review_score(filtered_orders)
row2[2].metric("Average Review Score", "—" if not avg_review == avg_review else f"{avg_review:.2f} / 5")

st.divider()

# --- Monthly revenue ----------------------------------------------------
st.subheader("Monthly Revenue")
monthly = m.monthly_summary(filtered_orders)
PARTIAL_MONTHS = {"2016-09", "2016-10", "2016-12"}
if monthly.empty:
    st.info("No delivered orders in the selected filters.")
else:
    st.plotly_chart(charts.monthly_revenue_chart(monthly, PARTIAL_MONTHS), width="stretch")
    st.caption(
        "Muted bars are partial periods at the dataset's edges (negligible pre-2017 volume) — not directly "
        "comparable to full months. Revenue growth has been primarily volume-driven; AOV has stayed within "
        "a narrow R$124–152 range throughout."
    )

st.divider()

# --- Category & state revenue ------------------------------------------
col1, col2 = st.columns(2)
with col1:
    st.subheader("Revenue by Category")
    cat_rev = m.revenue_by_category(filtered_items, top_n=10)
    if cat_rev.empty:
        st.info("No data for the selected filters.")
    else:
        st.plotly_chart(
            charts.horizontal_bar_chart(cat_rev, "product_category_english", "revenue", "Revenue (R$)"),
            width="stretch",
        )
        st.caption(
            "Top 10 of many categories. Revenue is broadly spread — no category exceeds ~10% of the total. "
            "An order can span multiple categories, so category order counts don't sum to total orders."
        )
with col2:
    st.subheader("Revenue by State")
    state_rev = m.revenue_by_state(filtered_orders)
    if state_rev.empty:
        st.info("No data for the selected filters.")
    else:
        st.plotly_chart(
            charts.horizontal_bar_chart(state_rev, "customer_state", "revenue", "Revenue (R$)"),
            width="stretch",
        )
        st.caption("São Paulo (SP) alone accounts for roughly a third of total revenue.")

st.divider()

# --- Delivery & reviews ---------------------------------------------------
col3, col4 = st.columns(2)
with col3:
    st.subheader("Delivery Performance")
    on_time_rate = m.on_time_delivery_rate(filtered_orders)
    if on_time_rate == on_time_rate:  # not NaN
        st.plotly_chart(charts.on_time_split_chart(on_time_rate), width="stretch")
        st.caption(f"{dashboard.format_percent(on_time_rate)} of orders with a known delivery date arrive on or "
                   "before the estimate. See Operations for delay-vs-review analysis.")
    else:
        st.info("No timing-eligible delivered orders in the selected filters.")
with col4:
    st.subheader("Review Score Distribution")
    if filtered_orders["is_delivered"].any():
        st.plotly_chart(charts.review_score_distribution_chart(filtered_orders), width="stretch")
        st.caption(f"{dashboard.format_percent(m.reviewed_order_rate(filtered_orders))} of delivered orders have "
                   "a review; scores skew positive.")
    else:
        st.info("No delivered orders in the selected filters.")

st.divider()

# --- Segment teaser (full customer base, independent of sidebar filters) --
st.subheader("Customer Segments")
customer_summary = seg.build_customer_summary(orders_analytics)
segmented = seg.assign_customer_segment(customer_summary)
segment_summary = (
    segmented.groupby("segment")
    .agg(customers=("customer_unique_id", "count"), total_revenue=("total_revenue", "sum"))
    .reset_index()
)
segment_summary["pct_of_customers"] = segment_summary["customers"] / segment_summary["customers"].sum() * 100
segment_summary["pct_of_revenue"] = segment_summary["total_revenue"] / segment_summary["total_revenue"].sum() * 100
st.plotly_chart(charts.segment_comparison_chart(segment_summary), width="stretch")
st.caption(
    "High-Value One-Time customers are less than a quarter of customers but over half of revenue — "
    "based on the full dataset, independent of the sidebar filters. See Customer Intelligence for detail."
)
