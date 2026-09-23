"""Customer-level retention, cohort, and segmentation logic (Phase 5).

RFM was evaluated and rejected as the segmentation method for this dataset:
97.0% of customers have Frequency = 1 (a single delivered order), which
leaves Frequency almost no variation to score on — a quintile-based RFM
would mostly be scoring Recency and Monetary value while Frequency
contributes noise. See build_rfm_suitability_report() and README.md
("Customer Retention & Segmentation") for the evidence behind this call.

Instead, customers are grouped by delivered-order count and observed
revenue into a small, transparent, threshold-documented segmentation (see
assign_customer_segment).

All functions use customer_unique_id and the delivered-order population,
consistent with src.metrics.
"""

from __future__ import annotations

import pandas as pd

from src.cleaning import filter_delivered_orders

# --------------------------------------------------------------------------
# Customer-level summary table
# --------------------------------------------------------------------------
def build_customer_summary(orders_analytics: pd.DataFrame, census_date: pd.Timestamp | None = None) -> pd.DataFrame:
    """One row per customer_unique_id with observed purchase history.

    `census_date` is the reference "as of" date for recency and window
    eligibility — it defaults to the latest purchase timestamp among
    delivered orders, since this is a closed historical dataset, not a live
    system. All measures here describe *observed* behavior within the
    dataset window, not a projected lifetime value.
    """
    delivered = filter_delivered_orders(orders_analytics)
    if census_date is None:
        census_date = delivered["order_purchase_timestamp"].max()

    summary = (
        delivered.groupby("customer_unique_id")
        .agg(
            delivered_order_count=("order_id", "nunique"),
            total_revenue=("item_revenue", "sum"),
            first_purchase_date=("order_purchase_timestamp", "min"),
            last_purchase_date=("order_purchase_timestamp", "max"),
            customer_state=("customer_state", lambda s: s.mode().iat[0]),
        )
        .reset_index()
    )
    summary["average_order_value"] = summary["total_revenue"] / summary["delivered_order_count"]
    summary["recency_days"] = (census_date - summary["last_purchase_date"]).dt.days
    summary["tenure_days"] = (summary["last_purchase_date"] - summary["first_purchase_date"]).dt.days
    summary["cohort_month"] = summary["first_purchase_date"].dt.to_period("M").astype(str)
    return summary


def time_to_second_purchase(orders_analytics: pd.DataFrame) -> pd.Series:
    """Days between a customer's first and second delivered order.

    Only includes customers with 2+ delivered orders (i.e. actual repeat
    customers) — this is a conditional statistic about return speed, not an
    overall retention probability (see retention_window_rate for that).
    Indexed by customer_unique_id.
    """
    delivered = filter_delivered_orders(orders_analytics).sort_values("order_purchase_timestamp")
    ranked = delivered.groupby("customer_unique_id")["order_purchase_timestamp"]
    first_two = ranked.apply(lambda s: s.iloc[1] - s.iloc[0] if len(s) >= 2 else pd.NaT)
    return first_two.dt.days.dropna().rename("days_to_second_purchase")


# --------------------------------------------------------------------------
# Retention windows, adjusted for right-censoring
# --------------------------------------------------------------------------
def retention_window_rate(
    orders_analytics: pd.DataFrame,
    window_days: int,
    census_date: pd.Timestamp | None = None,
) -> dict:
    """Eligibility-adjusted repeat-purchase rate within `window_days`.

    The dataset has a fixed end date, so a customer whose first purchase was
    less than `window_days` before the census date hasn't had time to be
    observed returning within that window — including them in the
    denominator would understate retention. Only customers with
    `census_date - first_purchase_date >= window_days` are eligible, and the
    rate is (eligible customers who returned within the window) / (eligible
    customers). This is a different, stricter number than the lifetime
    repeat_customer_rate in src.metrics, which has no time limit.
    """
    delivered = filter_delivered_orders(orders_analytics)
    if census_date is None:
        census_date = delivered["order_purchase_timestamp"].max()

    first_purchase = delivered.groupby("customer_unique_id")["order_purchase_timestamp"].min()
    days_observable = (census_date - first_purchase).dt.days
    eligible = days_observable[days_observable >= window_days].index

    t2p = time_to_second_purchase(orders_analytics)
    returned_within = t2p.reindex(eligible).le(window_days).fillna(False)

    n_eligible = len(eligible)
    n_returned = int(returned_within.sum())
    return {
        "window_days": window_days,
        "n_eligible": n_eligible,
        "n_returned": n_returned,
        "retention_rate": (n_returned / n_eligible) if n_eligible else float("nan"),
    }


# --------------------------------------------------------------------------
# Cohort retention matrix
# --------------------------------------------------------------------------
def build_cohort_retention_matrix(orders_analytics: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Monthly cohort retention matrix (% of each cohort active in month M0,
    M1, M2, ...), where cohort = month of a customer's first delivered
    order.

    Returns (matrix, cohort_sizes). `matrix` has NaN for any (cohort,
    period) combination that hasn't happened yet as of the dataset's last
    observed month — those are explicitly left blank, never filled with 0%,
    since a 0% there would misleadingly suggest the cohort churned rather
    than simply not having reached that month yet. A (cohort, period) that
    *is* observable but genuinely had no returning customers is correctly
    shown as 0%.
    """
    delivered = filter_delivered_orders(orders_analytics)
    order_month = delivered["order_purchase_timestamp"].dt.to_period("M")
    cohort_month = delivered.groupby("customer_unique_id")["order_purchase_timestamp"].transform("min").dt.to_period("M")

    events = pd.DataFrame({
        "customer_unique_id": delivered["customer_unique_id"],
        "cohort_month": cohort_month,
        "period_index": (order_month - cohort_month).apply(lambda x: x.n),
    })

    cohort_sizes = events.groupby("cohort_month")["customer_unique_id"].nunique().rename("cohort_size")
    active = (
        events.groupby(["cohort_month", "period_index"])["customer_unique_id"]
        .nunique()
        .rename("active_customers")
        .reset_index()
    )

    max_month = order_month.max()
    observable_rows = []
    for cohort in cohort_sizes.index:
        max_period = (max_month - cohort).n
        for period in range(max_period + 1):
            observable_rows.append((cohort, period))
    grid = pd.DataFrame(observable_rows, columns=["cohort_month", "period_index"])

    grid = grid.merge(active, on=["cohort_month", "period_index"], how="left")
    grid["active_customers"] = grid["active_customers"].fillna(0).astype(int)
    grid = grid.merge(cohort_sizes, on="cohort_month")
    grid["retention_rate"] = grid["active_customers"] / grid["cohort_size"]

    matrix = grid.pivot(index="cohort_month", columns="period_index", values="retention_rate")
    matrix.index = matrix.index.astype(str)

    cohort_sizes_df = cohort_sizes.reset_index()
    cohort_sizes_df["cohort_month"] = cohort_sizes_df["cohort_month"].astype(str)

    return matrix, cohort_sizes_df


# --------------------------------------------------------------------------
# RFM suitability check
# --------------------------------------------------------------------------
def build_rfm_suitability_report(customer_summary: pd.DataFrame) -> dict:
    """Summarizes Recency/Frequency/Monetary distributions so the RFM
    go/no-go decision is based on evidence, not assumption."""
    freq = customer_summary["delivered_order_count"]
    monetary = customer_summary["total_revenue"]
    recency = customer_summary["recency_days"]

    top10_cutoff = int(len(customer_summary) * 0.10)
    top10_share = (
        monetary.sort_values(ascending=False).head(top10_cutoff).sum() / monetary.sum()
        if top10_cutoff else float("nan")
    )

    return {
        "pct_frequency_equals_1": float((freq == 1).mean()),
        "frequency_value_counts": freq.value_counts(normalize=True).sort_index(),
        "monetary_median": float(monetary.median()),
        "monetary_mean": float(monetary.mean()),
        "monetary_skew": float(monetary.skew()),
        "monetary_p75": float(monetary.quantile(0.75)),
        "monetary_p90": float(monetary.quantile(0.90)),
        "top10pct_revenue_share": float(top10_share),
        "recency_median_days": float(recency.median()),
        "recency_std_days": float(recency.std()),
    }


# --------------------------------------------------------------------------
# Segmentation (behavior-based, not RFM — see module docstring)
# --------------------------------------------------------------------------
def assign_customer_segment(
    customer_summary: pd.DataFrame,
    high_value_percentile: float = 0.75,
    recent_window_days: int = 90,
) -> pd.DataFrame:
    """Assigns each customer to exactly one of 5 segments using two
    documented, data-driven thresholds rather than arbitrary cutoffs:

    - "High value" = total_revenue above the `high_value_percentile` of all
      customers' total_revenue (default: 75th percentile — top quartile).
    - "Recent" (for one-time customers only) = purchased within
      `recent_window_days` of the census date (default: 90 days, the same
      window used in retention_window_rate, for consistency).

    Segments (repeat status checked first, since it's the stronger behavioral
    signal, then value, then recency):
      High-Value Repeat   — 2+ orders, top-quartile revenue
      Repeat Customer     — 2+ orders, not top-quartile revenue
      High-Value One-Time — 1 order, top-quartile revenue
      One-Time Recent     — 1 order, not top-quartile revenue, purchased recently
      One-Time Lapsed     — 1 order, not top-quartile revenue, purchased long ago
    """
    df = customer_summary.copy()
    value_threshold = df["total_revenue"].quantile(high_value_percentile)

    is_repeat = df["delivered_order_count"] >= 2
    is_high_value = df["total_revenue"] > value_threshold
    is_recent = df["recency_days"] <= recent_window_days

    segment = pd.Series(pd.NA, index=df.index, dtype="object")
    segment[is_repeat & is_high_value] = "High-Value Repeat"
    segment[is_repeat & ~is_high_value] = "Repeat Customer"
    segment[~is_repeat & is_high_value] = "High-Value One-Time"
    segment[~is_repeat & ~is_high_value & is_recent] = "One-Time Recent"
    segment[~is_repeat & ~is_high_value & ~is_recent] = "One-Time Lapsed"

    df["segment"] = segment
    df.attrs["value_threshold"] = float(value_threshold)
    return df
