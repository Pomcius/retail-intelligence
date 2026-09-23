"""Core business metric calculations for Retail Intelligence.

Every function here operates on the delivered-order population by default
(see cleaning.COMPLETED_ORDER_STATUS) — the project's definition of a
completed, revenue-realized transaction — so the population rule lives in
one place instead of being re-filtered inconsistently across the codebase.
Each function's docstring states its exact denominator.

Functions take the cleaned orders_analytics DataFrame (from src.database),
not raw CSVs, and never hard-code results.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.cleaning import filter_delivered_orders


def total_revenue(orders_analytics: pd.DataFrame) -> float:
    """Product revenue only: SUM(item_revenue) across delivered orders.
    Excludes freight. This is revenue, not profit — the dataset has no
    cost-of-goods data."""
    delivered = filter_delivered_orders(orders_analytics)
    return float(delivered["item_revenue"].sum())


def order_count(orders_analytics: pd.DataFrame) -> int:
    """COUNT(DISTINCT order_id) across delivered orders."""
    delivered = filter_delivered_orders(orders_analytics)
    return int(delivered["order_id"].nunique())


def unique_customer_count(orders_analytics: pd.DataFrame) -> int:
    """COUNT(DISTINCT customer_unique_id) across delivered orders."""
    delivered = filter_delivered_orders(orders_analytics)
    return int(delivered["customer_unique_id"].nunique())


def average_order_value(orders_analytics: pd.DataFrame) -> float:
    """Delivered item revenue / delivered order count."""
    delivered = filter_delivered_orders(orders_analytics)
    orders = delivered["order_id"].nunique()
    return float(delivered["item_revenue"].sum() / orders) if orders else float("nan")


def customer_order_counts(orders_analytics: pd.DataFrame) -> pd.DataFrame:
    """Delivered order count and revenue per customer_unique_id — the basis
    for repeat-rate, purchase-frequency, and single-vs-repeat revenue splits.
    Uses customer_unique_id, never customer_id, since the same person can
    hold multiple customer_id values."""
    delivered = filter_delivered_orders(orders_analytics)
    return (
        delivered.groupby("customer_unique_id")
        .agg(delivered_order_count=("order_id", "nunique"), total_revenue=("item_revenue", "sum"))
        .reset_index()
    )


def repeat_customer_rate(orders_analytics: pd.DataFrame) -> float:
    """(customers with >= 2 delivered orders) / (customers with >= 1
    delivered order), keyed on customer_unique_id."""
    counts = customer_order_counts(orders_analytics)
    at_least_one = (counts["delivered_order_count"] >= 1).sum()
    at_least_two = (counts["delivered_order_count"] >= 2).sum()
    return float(at_least_two / at_least_one) if at_least_one else float("nan")


def average_review_score(orders_analytics: pd.DataFrame) -> float:
    """Mean of order-level avg_review_score among delivered orders that have
    review data. Orders with no review are excluded from the mean, never
    treated as a score of 0."""
    delivered = filter_delivered_orders(orders_analytics)
    return float(delivered["avg_review_score"].mean())


def reviewed_order_rate(orders_analytics: pd.DataFrame) -> float:
    """Share of delivered orders that have at least one review."""
    delivered = filter_delivered_orders(orders_analytics)
    return float(delivered["avg_review_score"].notna().mean())


def delivery_timing_eligible(orders_analytics: pd.DataFrame) -> pd.DataFrame:
    """Delivered orders where delivery_delay_days is known — i.e. an actual
    customer delivery date exists. Excludes the small number of orders
    marked 'delivered' with a missing delivery timestamp (a data anomaly,
    see notebooks/01_data_exploration.ipynb)."""
    delivered = filter_delivered_orders(orders_analytics)
    return delivered[delivered["delivery_delay_days"].notna()]


def on_time_delivery_rate(orders_analytics: pd.DataFrame) -> float:
    """(timing-eligible delivered orders with delivery_delay_days <= 0) /
    (timing-eligible delivered orders)."""
    eligible = delivery_timing_eligible(orders_analytics)
    if len(eligible) == 0:
        return float("nan")
    return float((eligible["delivery_delay_days"] <= 0).mean())


def late_delivery_rate(orders_analytics: pd.DataFrame) -> float:
    """(timing-eligible delivered orders with delivery_delay_days > 0) /
    (timing-eligible delivered orders). Equals 1 - on_time_delivery_rate."""
    eligible = delivery_timing_eligible(orders_analytics)
    if len(eligible) == 0:
        return float("nan")
    return float((eligible["delivery_delay_days"] > 0).mean())


def average_delivery_days(orders_analytics: pd.DataFrame) -> float:
    """Mean days from purchase to customer delivery, timing-eligible delivered orders."""
    eligible = delivery_timing_eligible(orders_analytics)
    return float(eligible["delivery_days"].mean())


def median_delivery_days(orders_analytics: pd.DataFrame) -> float:
    """Median days from purchase to customer delivery, timing-eligible delivered orders."""
    eligible = delivery_timing_eligible(orders_analytics)
    return float(eligible["delivery_days"].median())


def monthly_summary(orders_analytics: pd.DataFrame) -> pd.DataFrame:
    """Monthly revenue, order count, and AOV for delivered orders, keyed by
    the calendar month of order_purchase_timestamp. The first and last
    months in the result may be partial — see the caller for a completeness
    check before treating them as comparable to full months."""
    delivered = filter_delivered_orders(orders_analytics)
    period = delivered["order_purchase_timestamp"].dt.to_period("M")
    summary = (
        delivered.groupby(period)
        .agg(revenue=("item_revenue", "sum"), order_count=("order_id", "nunique"))
        .reset_index()
        .rename(columns={"order_purchase_timestamp": "month"})
    )
    summary["month"] = summary["month"].astype(str)
    summary["aov"] = summary["revenue"] / summary["order_count"]
    return summary


def revenue_by_category(order_items_analytics: pd.DataFrame, top_n: int | None = None) -> pd.DataFrame:
    """Revenue, item count, and order count by product category, at item
    grain (order_items_analytics), delivered items only. order_count values
    must not be summed across categories and reported as "total orders" —
    a single order can span multiple categories."""
    delivered_items = order_items_analytics[order_items_analytics["is_delivered"]]
    summary = (
        delivered_items.groupby("product_category_english")
        .agg(revenue=("price", "sum"), item_count=("order_item_id", "count"), order_count=("order_id", "nunique"))
        .reset_index()
        .sort_values("revenue", ascending=False)
    )
    summary["pct_of_revenue"] = summary["revenue"] / summary["revenue"].sum()
    return summary.head(top_n) if top_n else summary


def revenue_by_state(orders_analytics: pd.DataFrame) -> pd.DataFrame:
    """Revenue, orders, customers, and AOV by customer_state, delivered
    orders only."""
    delivered = filter_delivered_orders(orders_analytics)
    summary = (
        delivered.groupby("customer_state")
        .agg(revenue=("item_revenue", "sum"), orders=("order_id", "nunique"),
             customers=("customer_unique_id", "nunique"))
        .reset_index()
        .sort_values("revenue", ascending=False)
    )
    summary["aov"] = summary["revenue"] / summary["orders"]
    return summary


def review_score_by_delay_bucket(orders_analytics: pd.DataFrame) -> pd.DataFrame:
    """Average review score by delivery-delay bucket, among timing-eligible
    delivered orders. Bucket boundaries match sql/04_delivery_analysis.sql."""
    eligible = delivery_timing_eligible(orders_analytics).copy()
    order = ["Early >7d", "On-time / early", "1-3d late", "4-7d late", "8+d late"]
    conditions = [
        eligible["delivery_delay_days"] < -7,
        eligible["delivery_delay_days"] <= 0,
        eligible["delivery_delay_days"] <= 3,
        eligible["delivery_delay_days"] <= 7,
    ]
    eligible["delay_bucket"] = np.select(conditions, order[:4], default=order[4])

    summary = (
        eligible.groupby("delay_bucket")
        .agg(orders=("order_id", "nunique"), avg_review_score=("avg_review_score", "mean"))
        .reindex(order)
        .reset_index()
    )
    return summary


def state_delivery_summary(orders_analytics: pd.DataFrame) -> pd.DataFrame:
    """On-time rate, average delivery time, and average review score by
    customer_state, among timing-eligible delivered orders."""
    eligible = delivery_timing_eligible(orders_analytics)
    summary = (
        eligible.groupby("customer_state")
        .agg(timing_eligible_orders=("order_id", "nunique"),
             avg_delivery_days=("delivery_days", "mean"),
             avg_review_score=("avg_review_score", "mean"),
             on_time_orders=("delivery_delay_days", lambda s: (s <= 0).sum()))
        .reset_index()
    )
    summary["on_time_rate_pct"] = summary["on_time_orders"] / summary["timing_eligible_orders"] * 100
    return summary.sort_values("timing_eligible_orders", ascending=False)
