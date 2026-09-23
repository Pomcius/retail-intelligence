"""Load raw Olist CSV files from data/raw/ into pandas DataFrames."""

from pathlib import Path

import pandas as pd

RAW_DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

RAW_FILES = {
    "customers": "olist_customers_dataset.csv",
    "orders": "olist_orders_dataset.csv",
    "order_items": "olist_order_items_dataset.csv",
    "order_payments": "olist_order_payments_dataset.csv",
    "order_reviews": "olist_order_reviews_dataset.csv",
    "products": "olist_products_dataset.csv",
    "sellers": "olist_sellers_dataset.csv",
    "geolocation": "olist_geolocation_dataset.csv",
    "category_translation": "product_category_name_translation.csv",
}


def load_raw_tables(raw_dir: Path = RAW_DATA_DIR) -> dict[str, pd.DataFrame]:
    """Load every raw Olist CSV into a dict keyed by table name.

    Raises FileNotFoundError with a clear message if data/raw/ has not
    been populated yet (see data/raw/README.md for setup instructions).
    """
    tables = {}
    missing = []
    for name, filename in RAW_FILES.items():
        path = raw_dir / filename
        if not path.exists():
            missing.append(filename)
            continue
        tables[name] = pd.read_csv(path)

    if missing:
        raise FileNotFoundError(
            f"Missing raw data files in {raw_dir}: {missing}. "
            "See data/raw/README.md for download instructions."
        )
    return tables
