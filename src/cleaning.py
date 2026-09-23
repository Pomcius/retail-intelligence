"""Cleaning and analytical-modelling logic for the raw Olist tables.

Builds reusable, order-grain and item-grain tables from the raw CSVs. See
notebooks/01_data_exploration.ipynb for the cardinality/quality findings this
module is built to handle, and README.md ("Data Model") for a summary.
"""

from __future__ import annotations

import pandas as pd

# --------------------------------------------------------------------------
# Primary analytical population
# --------------------------------------------------------------------------
# "delivered" is the only status that represents a completed, realized
# transaction. Headline revenue/customer/AOV/retention/delivery KPIs must be
# computed over delivered orders only, so the definition lives in one place
# rather than being re-implemented (and risking drift) across the project.
# Other statuses (canceled, unavailable, shipped, processing, invoiced,
# created, approved) are preserved in orders_analytics via `is_delivered`
# for separate operational analysis — never silently dropped.
COMPLETED_ORDER_STATUS = "delivered"


def filter_delivered_orders(orders: pd.DataFrame) -> pd.DataFrame:
    """Return only orders with status == 'delivered'."""
    return orders[orders["order_status"] == COMPLETED_ORDER_STATUS].copy()


# --------------------------------------------------------------------------
# Timestamps
# --------------------------------------------------------------------------
ORDER_TIMESTAMP_COLUMNS = [
    "order_purchase_timestamp",
    "order_approved_at",
    "order_delivered_carrier_date",
    "order_delivered_customer_date",
    "order_estimated_delivery_date",
]
REVIEW_TIMESTAMP_COLUMNS = ["review_creation_date", "review_answer_timestamp"]


def parse_timestamps(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Convert the given columns to datetime, coercing bad values to NaT
    rather than fabricating dates. Genuine missingness is preserved."""
    df = df.copy()
    for col in columns:
        df[col] = pd.to_datetime(df[col], errors="coerce")
    return df


# --------------------------------------------------------------------------
# Order items: one row per item -> one row per order
# --------------------------------------------------------------------------
def build_order_items_summary(order_items: pd.DataFrame) -> pd.DataFrame:
    """Aggregate order_items (item grain) to order grain.

    item_revenue is product revenue only (sum of item price) and explicitly
    excludes freight — freight_value is kept separate and must never be
    treated as revenue or profit.
    """
    summary = (
        order_items.groupby("order_id")
        .agg(
            item_count=("order_item_id", "count"),
            unique_product_count=("product_id", "nunique"),
            unique_seller_count=("seller_id", "nunique"),
            item_revenue=("price", "sum"),
            freight_value=("freight_value", "sum"),
        )
        .reset_index()
    )
    return summary


# --------------------------------------------------------------------------
# Payments: 1+ rows per order -> one row per order
# --------------------------------------------------------------------------
def build_payments_summary(payments: pd.DataFrame) -> pd.DataFrame:
    """Aggregate order_payments (1+ rows per order, e.g. split payment
    methods) to order grain.

    Investigation (Phase 3): 9 payment rows have payment_value == 0.00 (none
    negative). They are either `voucher` rows with a fully-redeemed $0
    remainder or `not_defined`-type rows on canceled orders. None are the
    only payment row for a delivered order with nonzero total, so they don't
    distort total_payment_value — they are kept (not dropped) since summing
    a $0 row is a no-op and dropping rows without cause risks losing a real
    payment_type signal (e.g. a canceled order paid entirely by voucher).
    """
    summary = (
        payments.groupby("order_id")
        .agg(
            total_payment_value=("payment_value", "sum"),
            payment_record_count=("payment_sequential", "count"),
            max_installments=("payment_installments", "max"),
        )
        .reset_index()
    )
    primary_type = (
        payments.groupby("order_id")["payment_type"]
        .agg(lambda s: s.mode().iat[0])
        .rename("primary_payment_type")
    )
    summary = summary.merge(primary_type, on="order_id")
    summary["has_split_payment"] = summary["payment_record_count"] > 1
    return summary


# --------------------------------------------------------------------------
# Reviews: not-quite-1:1 with orders -> one row per order
# --------------------------------------------------------------------------
def build_reviews_summary(reviews: pd.DataFrame) -> pd.DataFrame:
    """Aggregate order_reviews to order grain.

    A small number of orders have more than one review row; this summarizes
    rather than arbitrarily picking one. Orders with zero review rows simply
    have no row here, so a left-join from orders_analytics leaves
    avg_review_score as NaN — missing reviews must never be treated as 0.
    """
    reviews = parse_timestamps(reviews, REVIEW_TIMESTAMP_COLUMNS)
    summary = (
        reviews.groupby("order_id")
        .agg(
            review_count=("review_id", "count"),
            avg_review_score=("review_score", "mean"),
            min_review_score=("review_score", "min"),
            max_review_score=("review_score", "max"),
            first_review_creation_date=("review_creation_date", "min"),
        )
        .reset_index()
    )
    return summary


# --------------------------------------------------------------------------
# Products: category translation with documented fallback
# --------------------------------------------------------------------------
def build_products_clean(products: pd.DataFrame, translation: pd.DataFrame) -> pd.DataFrame:
    """Attach an English category name with a two-step fallback:
    1. If a Portuguese category exists but has no translation row, keep the
       Portuguese name (2 categories affected — see notebook).
    2. If the product has no category at all, use "unknown" (610 products,
       1.85%) rather than dropping the row — those products still carry
       real revenue that must not disappear from category-level analysis.
    """
    products = products.copy()
    products = products.rename(columns={"product_category_name": "product_category_portuguese"})
    translated = products["product_category_portuguese"].map(
        translation.set_index("product_category_name")["product_category_name_english"]
    )
    products["product_category_english"] = (
        translated.fillna(products["product_category_portuguese"]).fillna("unknown")
    )
    return products


# --------------------------------------------------------------------------
# Geography: aggregate the noisy geolocation table to one row per zip prefix
# --------------------------------------------------------------------------
def build_geography_zip(geolocation: pd.DataFrame) -> pd.DataFrame:
    """Collapse geolocation (many rows per zip prefix, ~26% exact duplicates)
    to exactly one row per zip_code_prefix.

    lat/lng use the median (robust to occasional bad coordinates); city/state
    use the mode. Investigation (Phase 3): only 8 of 19,015 zip prefixes
    (0.04%) have more than one distinct state value, so the modal state is a
    safe, well-documented simplification. City names are far noisier (45% of
    prefixes have multiple spellings/neighbourhoods) — the modal city is a
    best-effort label, not a guarantee of correctness, and city-level
    analysis should prefer customers.customer_city / sellers.seller_city.
    """
    grouped = geolocation.groupby("geolocation_zip_code_prefix")
    summary = grouped.agg(
        lat=("geolocation_lat", "median"),
        lng=("geolocation_lng", "median"),
        city=("geolocation_city", lambda s: s.mode().iat[0]),
        state=("geolocation_state", lambda s: s.mode().iat[0]),
    ).reset_index()
    summary = summary.rename(columns={"geolocation_zip_code_prefix": "zip_code_prefix"})
    assert summary["zip_code_prefix"].is_unique, "geography_zip must be unique on zip_code_prefix"
    return summary


# --------------------------------------------------------------------------
# Canonical order-grain analytical table
# --------------------------------------------------------------------------
def build_orders_analytics(
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    order_items_summary: pd.DataFrame,
    payments_summary: pd.DataFrame,
    reviews_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Build the canonical one-row-per-order analytical table.

    Delivery delay is defined as (actual delivery date - estimated delivery
    date); a positive value means late. delivery_days/delivery_delay_days/
    is_late/is_on_time are left as missing (pd.NA), not False or 0, for any
    order without an actual delivery timestamp — this includes non-delivered
    orders and the 8 orders marked 'delivered' with no delivery timestamp
    (a data-quality anomaly, so they're excluded from delivery-timing
    metrics but still count toward revenue).
    """
    df = parse_timestamps(orders, ORDER_TIMESTAMP_COLUMNS)

    df = df.merge(
        customers[["customer_id", "customer_unique_id", "customer_city", "customer_state"]],
        on="customer_id",
        how="left",
    )
    df = df.merge(order_items_summary, on="order_id", how="left")
    df = df.merge(payments_summary, on="order_id", how="left")
    df = df.merge(reviews_summary, on="order_id", how="left")

    df["is_delivered"] = df["order_status"] == COMPLETED_ORDER_STATUS

    has_delivery_date = df["order_delivered_customer_date"].notna()

    df["delivery_days"] = pd.array([pd.NA] * len(df), dtype="Int64")
    df.loc[has_delivery_date, "delivery_days"] = (
        df.loc[has_delivery_date, "order_delivered_customer_date"]
        - df.loc[has_delivery_date, "order_purchase_timestamp"]
    ).dt.days

    df["delivery_delay_days"] = pd.array([pd.NA] * len(df), dtype="Int64")
    df.loc[has_delivery_date, "delivery_delay_days"] = (
        df.loc[has_delivery_date, "order_delivered_customer_date"]
        - df.loc[has_delivery_date, "order_estimated_delivery_date"]
    ).dt.days

    df["is_late"] = pd.array([pd.NA] * len(df), dtype="boolean")
    df.loc[has_delivery_date, "is_late"] = df.loc[has_delivery_date, "delivery_delay_days"] > 0

    df["is_on_time"] = pd.array([pd.NA] * len(df), dtype="boolean")
    df.loc[has_delivery_date, "is_on_time"] = df.loc[has_delivery_date, "delivery_delay_days"] <= 0

    assert df["order_id"].is_unique, "orders_analytics must be unique on order_id"
    assert len(df) == len(orders), "orders_analytics must not multiply order rows"

    return df


# --------------------------------------------------------------------------
# Item-grain analytical table (kept separate — do not force into order grain)
# --------------------------------------------------------------------------
def build_order_items_analytics(
    order_items: pd.DataFrame,
    orders: pd.DataFrame,
    customers: pd.DataFrame,
    sellers: pd.DataFrame,
    products_clean: pd.DataFrame,
) -> pd.DataFrame:
    """Build an item-grain table for product/category analysis that a
    one-row-per-order table would obscure (an order can span multiple
    categories). Stays at order_item grain — do not aggregate this further
    without an explicit, documented reason.
    """
    order_items = parse_timestamps(order_items, ["shipping_limit_date"])
    orders_ts = parse_timestamps(orders, ORDER_TIMESTAMP_COLUMNS)

    df = order_items.merge(
        orders_ts[["order_id", "customer_id", "order_status", "order_purchase_timestamp"]],
        on="order_id",
        how="left",
    )
    df = df.merge(
        customers[["customer_id", "customer_unique_id", "customer_state"]],
        on="customer_id",
        how="left",
    )
    df = df.merge(
        sellers[["seller_id", "seller_state", "seller_city"]],
        on="seller_id",
        how="left",
    )
    df = df.merge(
        products_clean[["product_id", "product_category_english", "product_category_portuguese"]],
        on="product_id",
        how="left",
    )
    df["is_delivered"] = df["order_status"] == COMPLETED_ORDER_STATUS

    assert len(df) == len(order_items), "order_items_analytics must not multiply item rows"

    return df
