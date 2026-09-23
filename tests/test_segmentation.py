"""Tests for src/segmentation.py: cohort retention, retention-window
eligibility (censoring), and customer segmentation.

Uses a small synthetic orders_analytics-shaped DataFrame with a known
cohort structure: one customer with 3 purchases 2 months apart, one with a
single purchase far in the past, one with a single purchase too recent to
be eligible for a 90-day window, and one non-delivered order that must be
excluded entirely.
"""

import pandas as pd
import pytest

from src import segmentation as seg


@pytest.fixture
def orders_analytics() -> pd.DataFrame:
    return pd.DataFrame({
        "order_id":            ["o1", "o2", "o3", "o4", "o5", "o6"],
        "customer_unique_id":  ["c1", "c1", "c1", "c2", "c3", "c4"],
        "order_status":        ["delivered"] * 5 + ["canceled"],
        "is_delivered":        [True, True, True, True, True, False],
        "order_purchase_timestamp": pd.to_datetime([
            "2018-01-01", "2018-03-01", "2018-05-01",  # c1: 3 orders, ~2 months apart
            "2017-01-15",                                # c2: single order, long ago
            "2018-05-25",                                # c3: single order, 5 days before census
            "2018-01-01",                                # c4: canceled, must be excluded
        ]),
        "item_revenue": [50.0, 60.0, 40.0, 500.0, 20.0, 999.0],
        "customer_state": ["SP", "SP", "SP", "RJ", "MG", "SP"],
    })


CENSUS_DATE = pd.Timestamp("2018-05-30")  # matches max purchase ts among delivered orders above


def test_customer_summary_excludes_non_delivered_and_reconciles(orders_analytics):
    summary = seg.build_customer_summary(orders_analytics, census_date=CENSUS_DATE)
    assert set(summary["customer_unique_id"]) == {"c1", "c2", "c3"}  # c4 excluded (canceled)
    c1 = summary.set_index("customer_unique_id").loc["c1"]
    assert c1["delivered_order_count"] == 3
    assert c1["total_revenue"] == 150.0
    assert c1["recency_days"] == (CENSUS_DATE - pd.Timestamp("2018-05-01")).days


def test_time_to_second_purchase_only_includes_repeat_customers(orders_analytics):
    t2p = seg.time_to_second_purchase(orders_analytics)
    assert list(t2p.index) == ["c1"]  # only c1 has 2+ delivered orders
    assert t2p.loc["c1"] == (pd.Timestamp("2018-03-01") - pd.Timestamp("2018-01-01")).days


def test_retention_window_rate_excludes_ineligible_customers(orders_analytics):
    # c3's first (only) purchase was 5 days before the census date, so it
    # cannot be eligible for a 90-day window regardless of outcome.
    result = seg.retention_window_rate(orders_analytics, window_days=90, census_date=CENSUS_DATE)
    assert result["n_eligible"] == 2  # c1 and c2 only; c3 excluded from the denominator
    assert result["n_returned"] == 1  # c1 returned within 90 days (Mar 1 is 59 days after Jan 1)


def test_cohort_matrix_m0_is_always_100pct_and_future_periods_are_nan(orders_analytics):
    matrix, cohort_sizes = seg.build_cohort_retention_matrix(orders_analytics)
    assert (matrix[0].dropna() == 1.0).all()
    assert (matrix.max(numeric_only=True) <= 1.0).all()
    # c2's 2017-01 cohort has had many months of observation by the 2018-05
    # dataset end, so most of those columns should be observable, not NaN
    assert matrix.loc["2017-01"].notna().sum() > 1
    # the most recent cohort (2018-05, c3) has only had period 0 observed
    assert matrix.loc["2018-05"].dropna().index.tolist() == [0]


def test_assign_customer_segment_covers_every_customer_exactly_once(orders_analytics):
    summary = seg.build_customer_summary(orders_analytics, census_date=CENSUS_DATE)
    segmented = seg.assign_customer_segment(summary)
    assert segmented["segment"].isna().sum() == 0
    assert segmented["segment"].nunique() <= 5
    # revenue must reconcile after segmentation (no customer dropped or duplicated)
    assert segmented["total_revenue"].sum() == pytest.approx(summary["total_revenue"].sum())
    # c1 (3 orders) must land in a repeat segment
    c1_segment = segmented.set_index("customer_unique_id").loc["c1", "segment"]
    assert c1_segment in {"Repeat Customer", "High-Value Repeat"}
