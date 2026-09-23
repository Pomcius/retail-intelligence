"""Operations — fulfillment performance and its relationship to reviews.

Answers: "Do delivery delays appear to affect customer satisfaction?"
(association, not proven causation).
"""

import streamlit as st

from src import charts, dashboard
from src import metrics as m

st.set_page_config(page_title="Operations | Retail Intelligence", layout="wide")
dashboard.apply_base_style()
dashboard.require_database()

orders_analytics = dashboard.load_orders_analytics()
filtered_orders = dashboard.render_sidebar_filters(orders_analytics)

st.title("Operations")
st.caption("Delivery performance and customer experience — timing metrics use only orders with a known delivery date.")

eligible = m.delivery_timing_eligible(filtered_orders)

if eligible.empty:
    st.info("No timing-eligible delivered orders in the selected filters.")
    st.stop()

# --- Headline delivery KPIs -----------------------------------------------
row = st.columns(5)
row[0].metric("On-Time Delivery Rate", dashboard.format_percent(m.on_time_delivery_rate(filtered_orders)))
row[1].metric("Late Delivery Rate", dashboard.format_percent(m.late_delivery_rate(filtered_orders)))
row[2].metric("Average Delivery Time", f"{m.average_delivery_days(filtered_orders):.1f} days")
row[3].metric("Median Delivery Time", f"{m.median_delivery_days(filtered_orders):.0f} days")
avg_review = m.average_review_score(filtered_orders)
row[4].metric("Average Review Score", "—" if avg_review != avg_review else f"{avg_review:.2f} / 5")

st.caption(
    f"{len(eligible):,} of {m.order_count(filtered_orders):,} delivered orders have a known delivery date "
    "and are used for the timing metrics above; a small number of orders marked 'delivered' with no delivery "
    "timestamp (a data anomaly) are excluded from timing metrics only, not from revenue/order/customer KPIs."
)

st.divider()

# --- Delivery delay vs review score ----------------------------------------
st.subheader("Delivery Delay vs. Review Score")
bucket_summary = m.review_score_by_delay_bucket(filtered_orders)
st.plotly_chart(charts.delay_bucket_review_chart(bucket_summary), width="stretch")
on_time_score = eligible.loc[eligible["delivery_delay_days"] <= 0, "avg_review_score"].mean()
late_score = eligible.loc[eligible["delivery_delay_days"] > 0, "avg_review_score"].mean()
st.caption(
    f"Late deliveries are associated with substantially lower customer review scores: on-time/early orders "
    f"average {on_time_score:.2f}/5 versus {late_score:.2f}/5 for late orders, falling steadily as delay "
    "increases. This is an association observed in the data, not evidence that lateness *causes* the lower score."
)

st.divider()

# --- Delivery time distribution ---------------------------------------
st.subheader("Delivery Time Distribution")
st.plotly_chart(charts.delivery_time_histogram(eligible), width="stretch")
st.caption("Delivery time is right-skewed: most orders arrive well before the estimate, with a long tail of slower deliveries.")

st.divider()

# --- State-level operations -------------------------------------------------
st.subheader("Delivery Performance by State")
state_summary = m.state_delivery_summary(filtered_orders)
st.plotly_chart(charts.state_operations_chart(state_summary), width="stretch")
st.caption(
    "Restricted to states with at least 100 timing-eligible orders, to avoid comparing small samples. "
    "Rio de Janeiro (RJ) stands out: despite being the #2 state by order volume, it has a notably lower "
    "on-time rate (87.9%) and average review score (3.97) than São Paulo (95.5%, 4.25) or other high-volume "
    "states — worth investigating, not assumed to be caused by any single factor."
)
