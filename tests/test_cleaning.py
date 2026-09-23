"""Tests for the core Phase 3 transformation logic in src/cleaning.py.

Uses small synthetic DataFrames rather than the raw dataset so tests run
fast and exercise specific edge cases (missing reviews, split payments,
untranslated categories, undelivered orders) deliberately.
"""

import pandas as pd

from src.cleaning import (
    build_geography_zip,
    build_order_items_summary,
    build_orders_analytics,
    build_payments_summary,
    build_products_clean,
    build_reviews_summary,
    filter_delivered_orders,
)


def test_filter_delivered_orders_keeps_only_delivered():
    orders = pd.DataFrame({
        "order_id": ["o1", "o2", "o3"],
        "order_status": ["delivered", "canceled", "shipped"],
    })
    result = filter_delivered_orders(orders)
    assert result["order_id"].tolist() == ["o1"]


def test_order_items_summary_aggregates_to_order_grain():
    order_items = pd.DataFrame({
        "order_id": ["o1", "o1", "o2"],
        "order_item_id": [1, 2, 1],
        "product_id": ["p1", "p2", "p1"],
        "seller_id": ["s1", "s1", "s2"],
        "price": [10.0, 20.0, 5.0],
        "freight_value": [1.0, 2.0, 0.5],
    })
    summary = build_order_items_summary(order_items)

    o1 = summary.set_index("order_id").loc["o1"]
    assert o1["item_count"] == 2
    assert o1["unique_product_count"] == 2
    assert o1["unique_seller_count"] == 1
    assert o1["item_revenue"] == 30.0
    assert o1["freight_value"] == 3.0
    # revenue must reconcile with the raw total — no double counting
    assert summary["item_revenue"].sum() == order_items["price"].sum()


def test_payments_summary_sums_split_payments():
    payments = pd.DataFrame({
        "order_id": ["o1", "o1", "o2"],
        "payment_sequential": [1, 2, 1],
        "payment_type": ["voucher", "credit_card", "boleto"],
        "payment_installments": [1, 3, 1],
        "payment_value": [10.0, 40.0, 25.0],
    })
    summary = build_payments_summary(payments).set_index("order_id")

    assert summary.loc["o1", "total_payment_value"] == 50.0
    assert summary.loc["o1", "payment_record_count"] == 2
    assert summary.loc["o1", "has_split_payment"] is True or bool(summary.loc["o1", "has_split_payment"])
    assert bool(summary.loc["o2", "has_split_payment"]) is False


def test_reviews_summary_treats_missing_reviews_as_missing_not_zero():
    reviews = pd.DataFrame({
        "order_id": ["o1", "o1"],
        "review_id": ["r1", "r2"],
        "review_score": [5, 3],
        "review_comment_title": [None, None],
        "review_comment_message": [None, None],
        "review_creation_date": ["2018-01-01", "2018-01-05"],
        "review_answer_timestamp": ["2018-01-02", "2018-01-06"],
    })
    summary = build_reviews_summary(reviews)

    # order o1 has two review rows -> averaged, not picked arbitrarily
    assert summary.loc[summary["order_id"] == "o1", "avg_review_score"].iat[0] == 4.0

    # an order with no review row at all must end up NaN after merge, never 0
    orders_analytics_like = pd.DataFrame({"order_id": ["o1", "o2"]}).merge(summary, on="order_id", how="left")
    assert orders_analytics_like.loc[orders_analytics_like["order_id"] == "o2", "avg_review_score"].isna().all()


def test_products_clean_category_fallback():
    products = pd.DataFrame({
        "product_id": ["p1", "p2", "p3"],
        "product_category_name": ["cama_mesa_banho", "pc_gamer", None],
    })
    translation = pd.DataFrame({
        "product_category_name": ["cama_mesa_banho"],
        "product_category_name_english": ["bed_bath_table"],
    })
    result = build_products_clean(products, translation).set_index("product_id")

    assert result.loc["p1", "product_category_english"] == "bed_bath_table"
    # category present but no translation row -> fall back to Portuguese name
    assert result.loc["p2", "product_category_english"] == "pc_gamer"
    # no category at all -> "unknown", not dropped
    assert result.loc["p3", "product_category_english"] == "unknown"
    assert result["product_category_english"].notna().all()


def test_geography_zip_unique_and_uses_median():
    geolocation = pd.DataFrame({
        "geolocation_zip_code_prefix": [1001, 1001, 1001, 2002],
        "geolocation_lat": [-23.0, -23.5, -23.25, -10.0],
        "geolocation_lng": [-46.0, -46.5, -46.25, -50.0],
        "geolocation_city": ["sao paulo", "sao paulo", "SP", "recife"],
        "geolocation_state": ["SP", "SP", "SP", "PE"],
    })
    result = build_geography_zip(geolocation).set_index("zip_code_prefix")

    assert result.index.is_unique
    assert result.loc[1001, "lat"] == -23.25  # median of the three values
    assert result.loc[1001, "state"] == "SP"


def test_orders_analytics_delivery_flags_missing_when_no_delivery_date():
    orders = pd.DataFrame({
        "order_id": ["o1", "o2"],
        "customer_id": ["c1", "c2"],
        "order_status": ["delivered", "shipped"],
        "order_purchase_timestamp": ["2018-01-01", "2018-01-01"],
        "order_approved_at": ["2018-01-01", "2018-01-01"],
        "order_delivered_carrier_date": ["2018-01-02", None],
        "order_delivered_customer_date": ["2018-01-10", None],
        "order_estimated_delivery_date": ["2018-01-05", "2018-01-20"],
    })
    customers = pd.DataFrame({
        "customer_id": ["c1", "c2"],
        "customer_unique_id": ["u1", "u2"],
        "customer_city": ["sp", "rj"],
        "customer_state": ["SP", "RJ"],
    })
    empty_items = pd.DataFrame(columns=["order_id", "item_count", "unique_product_count",
                                         "unique_seller_count", "item_revenue", "freight_value"])
    empty_payments = pd.DataFrame(columns=["order_id", "total_payment_value", "payment_record_count",
                                            "max_installments", "primary_payment_type", "has_split_payment"])
    empty_reviews = pd.DataFrame(columns=["order_id", "review_count", "avg_review_score",
                                           "min_review_score", "max_review_score", "first_review_creation_date"])

    result = build_orders_analytics(orders, customers, empty_items, empty_payments, empty_reviews)
    result = result.set_index("order_id")

    # o1: delivered 5 days late (Jan 10 actual vs Jan 5 estimated)
    assert result.loc["o1", "delivery_delay_days"] == 5
    assert bool(result.loc["o1", "is_late"]) is True

    # o2: never delivered -> delivery fields must be missing, not False/0
    assert pd.isna(result.loc["o2", "delivery_delay_days"])
    assert pd.isna(result.loc["o2", "is_late"])
    assert pd.isna(result.loc["o2", "is_on_time"])

    assert result.index.is_unique
