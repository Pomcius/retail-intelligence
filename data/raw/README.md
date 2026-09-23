# Raw data

This project uses the [Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce) (Kaggle).

The raw CSVs are not committed to this repository (see `.gitignore`) to keep the repo lightweight and respect the dataset's distribution terms. Download the dataset from Kaggle and place the following files directly in this folder:

- `olist_customers_dataset.csv`
- `olist_orders_dataset.csv`
- `olist_order_items_dataset.csv`
- `olist_order_payments_dataset.csv`
- `olist_order_reviews_dataset.csv`
- `olist_products_dataset.csv`
- `olist_sellers_dataset.csv`
- `olist_geolocation_dataset.csv`
- `product_category_name_translation.csv`

Once the files are in place, `src/data_loader.py` will load them for cleaning and analysis.
