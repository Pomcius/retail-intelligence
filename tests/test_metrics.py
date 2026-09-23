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
