"""Recommendations — evidence-based findings translated into suggested actions.

Every recommendation follows Finding -> Evidence -> Business Implication ->
Suggested Action, and is backed by numbers already calculated and validated
in Phases 4-5 (see src/metrics.py, src/segmentation.py). These are
hypotheses worth testing, not proven outcomes or ROI projections.
"""

import streamlit as st

from src import dashboard

st.set_page_config(page_title="Recommendations | Retail Intelligence", layout="wide")
dashboard.apply_base_style()
dashboard.require_database()

st.title("Recommendations")
st.caption("Evidence-based findings and suggested next steps — not proven outcomes.")

st.info(
    "Each item below follows **Finding → Evidence → Business Implication → Suggested Action**. "
    "Actions are directions worth testing, not guaranteed results — this dataset supports association, "
    "not a measured ROI for any specific intervention.",
    icon=":material/info:",
)


def recommendation(title: str, finding: str, evidence: str, implication: str, action: str) -> None:
    st.subheader(title)
    st.markdown(f"**Finding.** {finding}")
    st.markdown(f"**Evidence.** {evidence}")
    st.markdown(f"**Business implication.** {implication}")
    st.markdown(f"**Suggested action.** {action}")
    st.divider()


recommendation(
    "A. Customer Retention Is Extremely Low",
    "The vast majority of customers never make a second delivered purchase.",
    "3.0% lifetime repeat-customer rate (2,801 of 93,358 customers); eligibility-adjusted retention is even "
    "lower in the short term — 1.6% at 30 days, rising to 3.1% at 180 days.",
    "Revenue growth is driven almost entirely by new-customer acquisition, not repeat purchasing. Retention "
    "improvements have a low current base to grow from, which is itself an opportunity.",
    "Test structured post-purchase retention campaigns (e.g. a follow-up offer or reminder) timed within "
    "the first 30–90 days after a customer's first delivery, since most customers who do return do so within "
    "that window (median time to second order: 28 days).",
)

recommendation(
    "B. High-Value One-Time Customers Represent a Large Share of Revenue",
    "A relatively small group of high-value one-time buyers accounts for a disproportionately large share "
    "of observed revenue.",
    "High-Value One-Time customers are 23.2% of customers but 57.8% of total revenue — more than double any "
    "other segment (see Customer Intelligence).",
    "This segment is high-value strictly by order size, not purchase frequency — they've shown willingness "
    "to spend, but nothing yet indicates they'll return on their own.",
    "Prioritize retention experiments (targeted follow-up, incentive to reorder) toward high-value first-time "
    "buyers specifically, rather than a blanket campaign to all one-time customers.",
)

recommendation(
    "C. Delivery Delays Are Strongly Associated with Lower Reviews",
    "Late deliveries are associated with substantially worse customer review scores.",
    "On-time/early orders average 4.29/5 vs. 2.27/5 for late orders, falling monotonically across delay "
    "buckets (4.32 → 1.70 from \"early by >7 days\" to \"8+ days late\"). This is an association in "
    "observational data, not proof that delay *causes* the lower score.",
    "Even without proving causation, the pattern is large and consistent enough to be a genuine operational "
    "signal worth acting on.",
    "Identify the seller/state combinations with consistently high late-delivery rates (see Operations) and "
    "prioritize operational or logistics improvements there first, rather than treating delivery performance "
    "as uniform nationally.",
)

recommendation(
    "D. Rio de Janeiro Underperforms Its Commercial Importance",
    "RJ is the second-largest state by order volume and revenue, but has weaker delivery and review "
    "performance than São Paulo.",
    "RJ: 87.9% on-time delivery, 3.97 average review score. SP: 95.5% on-time, 4.25 average review score — "
    "despite RJ having the 2nd-highest order volume of any state.",
    "A high-volume state with below-average operational performance is a concentrated source of dissatisfied "
    "customers, not a diffuse, low-priority issue.",
    "Investigate seller and logistics performance specific to RJ (e.g. carrier lanes, seller concentration, "
    "warehouse distance) to identify whether the gap is addressable operationally, before assuming it's "
    "explained by geography alone.",
)

st.caption(
    "All figures on this page are computed in src/metrics.py and src/segmentation.py and validated against "
    "independent SQL queries in sql/ — see README.md for full methodology and limitations."
)
