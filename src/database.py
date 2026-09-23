"""Build and connect to the project's DuckDB analytical database.

Run `python -m src.database` to (re)build data/processed/retail_intelligence.duckdb
from the raw CSVs in data/raw/. The generated .duckdb file is gitignored —
this script is the reproducible source of truth for it.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from src import cleaning
from src.data_loader import load_raw_tables

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "processed" / "retail_intelligence.duckdb"
# Minimal committed database the dashboard reads (see src/export_dashboard_db.py).
DASHBOARD_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "dashboard.duckdb"


def build_analytical_tables(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Run all Phase 3 cleaning/aggregation steps and return every analytical
    table, keyed by the name it will be stored under in DuckDB."""
    order_items_summary = cleaning.build_order_items_summary(raw["order_items"])
    payments_order_summary = cleaning.build_payments_summary(raw["order_payments"])
    reviews_order_summary = cleaning.build_reviews_summary(raw["order_reviews"])
    products_clean = cleaning.build_products_clean(raw["products"], raw["category_translation"])
    geography_zip = cleaning.build_geography_zip(raw["geolocation"])

    orders_analytics = cleaning.build_orders_analytics(
        raw["orders"],
        raw["customers"],
        order_items_summary,
        payments_order_summary,
        reviews_order_summary,
    )
    order_items_analytics = cleaning.build_order_items_analytics(
        raw["order_items"],
        raw["orders"],
        raw["customers"],
        raw["sellers"],
        products_clean,
    )

    return {
        "order_items_summary": order_items_summary,
        "payments_order_summary": payments_order_summary,
        "reviews_order_summary": reviews_order_summary,
        "products_clean": products_clean,
        "geography_zip": geography_zip,
        "orders_analytics": orders_analytics,
        "order_items_analytics": order_items_analytics,
    }


def validate_analytical_tables(raw: dict[str, pd.DataFrame], tables: dict[str, pd.DataFrame]) -> bool:
    """Reconcile analytical tables against the raw data. Returns True if every
    check passes; prints a report either way. Raises on structural failures
    (uniqueness, row-count multiplication) since those would silently corrupt
    every downstream metric.
    """
    orders_analytics = tables["orders_analytics"]
    order_items_analytics = tables["order_items_analytics"]
    geography_zip = tables["geography_zip"]
    products_clean = tables["products_clean"]

    assert orders_analytics["order_id"].is_unique, "orders_analytics is not unique on order_id"
    assert len(orders_analytics) == len(raw["orders"]), "orders_analytics row count changed vs raw orders"
    assert len(order_items_analytics) == len(raw["order_items"]), "order_items_analytics multiplied item rows"
    assert geography_zip["zip_code_prefix"].is_unique, "geography_zip is not unique on zip_code_prefix"
    assert products_clean["product_category_english"].notna().all(), "product_category_english has nulls after fallback"
    assert orders_analytics["customer_unique_id"].notna().all(), "orders_analytics lost a customer_unique_id"

    checks = []

    raw_item_revenue = round(raw["order_items"]["price"].sum(), 2)
    agg_item_revenue = round(orders_analytics["item_revenue"].sum(), 2)
    checks.append(("item_revenue reconciles to raw order_items.price", abs(raw_item_revenue - agg_item_revenue) < 0.01,
                    f"raw={raw_item_revenue:,.2f} agg={agg_item_revenue:,.2f}"))

    raw_payment_total = round(raw["order_payments"]["payment_value"].sum(), 2)
    agg_payment_total = round(orders_analytics["total_payment_value"].sum(), 2)
    checks.append(("total_payment_value reconciles to raw order_payments.payment_value",
                    abs(raw_payment_total - agg_payment_total) < 0.01,
                    f"raw={raw_payment_total:,.2f} agg={agg_payment_total:,.2f}"))

    raw_review_rows = len(raw["order_reviews"])
    agg_review_rows = int(orders_analytics["review_count"].sum())
    checks.append(("review_count sums to raw order_reviews row count", raw_review_rows == agg_review_rows,
                    f"raw={raw_review_rows} agg={agg_review_rows}"))

    delivered_raw = int((raw["orders"]["order_status"] == cleaning.COMPLETED_ORDER_STATUS).sum())
    delivered_agg = int(orders_analytics["is_delivered"].sum())
    checks.append(("delivered-order count matches raw order_status filter", delivered_raw == delivered_agg,
                    f"raw={delivered_raw} agg={delivered_agg}"))

    both_late_and_on_time = (
        orders_analytics["is_late"].fillna(False) & orders_analytics["is_on_time"].fillna(False)
    ).sum()
    checks.append(("is_late and is_on_time are mutually exclusive", both_late_and_on_time == 0,
                    f"conflicting rows={both_late_and_on_time}"))

    delivery_fields_only_when_delivered_date_present = (
        orders_analytics.loc[orders_analytics["order_delivered_customer_date"].isna(), "delivery_delay_days"]
        .isna()
        .all()
    )
    checks.append(("delivery_delay_days is null whenever there is no delivery date",
                    delivery_fields_only_when_delivered_date_present, ""))

    all_passed = all(passed for _, passed, _ in checks)
    print("Validation report:")
    for name, passed, detail in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}" + (f" ({detail})" if detail else ""))
    return all_passed


def build_database(db_path: Path = DB_PATH) -> None:
    """Load raw CSVs, build every analytical table, validate them, and write
    them to DuckDB."""
    raw = load_raw_tables()
    tables = build_analytical_tables(raw)

    if not validate_analytical_tables(raw, tables):
        raise AssertionError("One or more analytical-table validations failed — see report above.")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path))
    for name, df in tables.items():
        con.register("_tmp_df", df)
        con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM _tmp_df")
        con.unregister("_tmp_df")
    con.close()
    print(f"\nWrote {len(tables)} tables to {db_path}")


def get_connection(db_path: Path = DB_PATH, read_only: bool = True) -> duckdb.DuckDBPyConnection:
    """Connect to the built analytical database. Raises a clear error if the file is missing."""
    if not db_path.exists():
        raise FileNotFoundError(f"{db_path} not found — run `python -m src.database` to build it.")
    return duckdb.connect(str(db_path), read_only=read_only)


if __name__ == "__main__":
    build_database()
