"""Export the minimal, self-contained database the Streamlit dashboard reads.

Run `python -m src.export_dashboard_db` after `python -m src.database` to
write data/dashboard.duckdb: only the two tables and the columns the
dashboard actually uses, copied unchanged from the full analytical database.
This file is committed so the deployed app needs no raw CSVs or Kaggle access;
the full pipeline (raw CSVs -> src.database) remains the reproducible source.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

from src.database import DB_PATH as FULL_DB_PATH, DASHBOARD_DB_PATH

DASHBOARD_COLUMNS = {
    "orders_analytics": [
        "order_id", "customer_id", "customer_unique_id", "customer_state", "order_status",
        "order_purchase_timestamp", "is_delivered", "item_revenue", "item_count",
        "avg_review_score", "delivery_days", "delivery_delay_days",
    ],
    "order_items_analytics": [
        "order_id", "order_item_id", "customer_unique_id", "customer_state",
        "order_purchase_timestamp", "product_category_english", "price", "is_delivered",
    ],
}


def export_dashboard_db(source: Path = FULL_DB_PATH, target: Path = DASHBOARD_DB_PATH) -> None:
    if not source.exists():
        raise FileNotFoundError(f"{source} not found — run `python -m src.database` first.")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.unlink(missing_ok=True)

    con = duckdb.connect(str(target))
    con.execute(f"ATTACH '{source}' AS full_db (READ_ONLY)")
    for table, cols in DASHBOARD_COLUMNS.items():
        con.execute(f"CREATE TABLE {table} AS SELECT {', '.join(cols)} FROM full_db.{table} ORDER BY order_id")
    con.execute("DETACH full_db")
    con.close()
    print(f"Wrote {target} ({target.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    export_dashboard_db()
