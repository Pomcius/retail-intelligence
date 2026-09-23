"""Tests for the core KPI functions in src/metrics.py.

Uses a small synthetic orders_analytics-shaped DataFrame that deliberately
includes non-delivered orders, a repeat customer, a missing review, and a
missing delivery timestamp — the edge cases each metric must handle
correctly per its documented population definition.
"""

import pandas as pd
import pytest

from src import metrics as m


@pytest.fixture
def orders_analytics() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id":            ["o1", "o2", "o3", "o4", "o5"],
        "customer_unique_id":  ["c1", "c1", "c2", "c3", "c4"],
        "order_status":        ["delivered", "delivered", "delivered", "delivered", "canceled"],
        "is_delivered":        [True, True, True, True, False],
        "order_purchase_timestamp": pd.to_datetime(
            ["2018-01-01", "2018-02-01", "2018-01-15", "2018-03-01", "2018-01-10"]
        ),
        "item_revenue":        [100.0, 50.0, 200.0, 80.0, 999.0],
        # o1: 5 days late, o2: on time, o3: no delivery timestamp (anomaly), o4: 3 days early, o5: n/a (not delivered)
        "delivery_days":       pd.array([10, 8, pd.NA, 6, pd.NA], dtype="Int64"),
        "delivery_delay_days": pd.array([5, -1, pd.NA, -3, pd.NA], dtype="Int64"),
        "avg_review_score":    [2.0, 5.0, None, 4.0, 1.0],
        "customer_state":      ["SP", "SP", "RJ", "MG", "SP"],
    })


@pytest.fixture
def order_items_analytics() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id":        ["o1", "o1", "o2", "o3"],
        "order_item_id":   [1, 2, 1, 1],
        "is_delivered":    [True, True, True, False],
        "price":           [60.0, 40.0, 50.0, 999.0],
        "product_category_english": ["toys", "books", "toys", "toys"],
    })


def test_total_revenue_excludes_non_delivered(orders_analytics):
    # 100 + 50 + 200 + 80 delivered; the 999 canceled order must be excluded
    assert m.total_revenue(orders_analytics) == 430.0


def test_order_count_and_customer_count(orders_analytics):
    assert m.order_count(orders_analytics) == 4
    assert m.unique_customer_count(orders_analytics) == 3  # c1 counted once despite 2 orders


def test_average_order_value(orders_analytics):
    assert m.average_order_value(orders_analytics) == pytest.approx(430.0 / 4)


def test_repeat_customer_rate(orders_analytics):
    # c1 has 2 delivered orders; c2, c3 have 1 each -> 1 of 3 customers repeats
    assert m.repeat_customer_rate(orders_analytics) == pytest.approx(1 / 3)


def test_average_review_score_ignores_missing_review(orders_analytics):
    # o3's review is missing and must not be treated as 0
    assert m.average_review_score(orders_analytics) == pytest.approx((2.0 + 5.0 + 4.0) / 3)


def test_reviewed_order_rate(orders_analytics):
    assert m.reviewed_order_rate(orders_analytics) == pytest.approx(3 / 4)


def test_delivery_timing_eligible_excludes_missing_delivery_date(orders_analytics):
    eligible = m.delivery_timing_eligible(orders_analytics)
    # o3 (no delivery date) and o5 (not delivered) must both be excluded
    assert set(eligible["order_id"]) == {"o1", "o2", "o4"}


def test_on_time_and_late_delivery_rate(orders_analytics):
    # of the 3 timing-eligible orders: o1 late, o2 on-time, o4 on-time (early)
    assert m.on_time_delivery_rate(orders_analytics) == pytest.approx(2 / 3)
    assert m.late_delivery_rate(orders_analytics) == pytest.approx(1 / 3)
    assert m.on_time_delivery_rate(orders_analytics) + m.late_delivery_rate(orders_analytics) == pytest.approx(1.0)


def test_average_and_median_delivery_days(orders_analytics):
    assert m.average_delivery_days(orders_analytics) == pytest.approx((10 + 8 + 6) / 3)
    assert m.median_delivery_days(orders_analytics) == 8.0


def test_monthly_summary_groups_by_purchase_month(orders_analytics):
    summary = m.monthly_summary(orders_analytics).set_index("month")
    assert summary.loc["2018-01", "revenue"] == 300.0  # o1 + o3
    assert summary.loc["2018-01", "order_count"] == 2
    assert summary.loc["2018-02", "revenue"] == 50.0


def test_revenue_by_category_excludes_non_delivered_items(order_items_analytics):
    result = m.revenue_by_category(order_items_analytics).set_index("product_category_english")
    # o3 (non-delivered, 999.0) must not appear anywhere
    assert result["revenue"].sum() == pytest.approx(60.0 + 40.0 + 50.0)
    assert result.loc["toys", "revenue"] == pytest.approx(110.0)
    assert result.loc["toys", "order_count"] == 2  # o1 and o2, not summed with books' order
    assert result["pct_of_revenue"].sum() == pytest.approx(1.0)


def test_revenue_by_state_excludes_non_delivered(orders_analytics):
    result = m.revenue_by_state(orders_analytics).set_index("customer_state")
    # o5 (canceled, SP, 999.0) must not inflate SP's revenue
    assert result.loc["SP", "revenue"] == pytest.approx(150.0)  # o1 + o2
    assert result.loc["SP", "customers"] == 1  # c1 only (o5 excluded, and c1 counted once)


def test_review_score_by_delay_bucket_assigns_correct_buckets(orders_analytics):
    result = m.review_score_by_delay_bucket(orders_analytics).set_index("delay_bucket")
    # o1: delay=5 -> "1-3d late"? no: 5 is >3 and <=7 -> "4-7d late"
    assert result.loc["4-7d late", "avg_review_score"] == 2.0
    # o2: delay=-1 -> "On-time / early"; o4: delay=-3 -> "On-time / early"
    assert result.loc["On-time / early", "orders"] == 2
    assert result.loc["On-time / early", "avg_review_score"] == pytest.approx((5.0 + 4.0) / 2)
    # o3 (no delivery date) must not appear in any bucket
    assert result["orders"].sum() == 3


def test_state_delivery_summary_uses_timing_eligible_only(orders_analytics):
    result = m.state_delivery_summary(orders_analytics).set_index("customer_state")
    # SP has o1 (late) and o2 (on-time) timing-eligible; o5 excluded (not delivered)
    assert result.loc["SP", "timing_eligible_orders"] == 2
    assert result.loc["SP", "on_time_rate_pct"] == pytest.approx(50.0)
    # RJ's only order (o3) has no delivery timestamp -> RJ shouldn't appear at all
    assert "RJ" not in result.index
