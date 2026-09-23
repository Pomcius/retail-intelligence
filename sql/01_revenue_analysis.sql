-- Revenue analysis
-- Population: delivered orders only (orders_analytics.is_delivered).
-- Revenue = SUM(item_revenue), i.e. product revenue only — freight is excluded
-- and this is never treated as profit (no cost-of-goods data exists).
-- Run against data/processed/retail_intelligence.duckdb.

-- 1. Headline totals -----------------------------------------------------
SELECT
    SUM(item_revenue)                       AS total_revenue,
    COUNT(DISTINCT order_id)                AS delivered_orders,
    SUM(item_revenue) / COUNT(DISTINCT order_id) AS average_order_value
FROM orders_analytics
WHERE is_delivered;

-- 2. Monthly revenue, order volume, and AOV trend -------------------------
-- The first (2016-09/10/12) and last (2018-08) months are partial: the
-- marketplace had negligible volume before 2017, and orders placed after
-- ~2018-08 hadn't had time to reach "delivered" status when this dataset
-- was extracted. They should not be compared directly to full months.
SELECT
    strftime(order_purchase_timestamp, '%Y-%m') AS month,
    SUM(item_revenue)                            AS revenue,
    COUNT(DISTINCT order_id)                     AS order_count,
    SUM(item_revenue) / COUNT(DISTINCT order_id)  AS aov
FROM orders_analytics
WHERE is_delivered
GROUP BY month
ORDER BY month;

-- 3. Month-over-month revenue growth --------------------------------------
-- Uses a window function (LAG) rather than a Python groupby+shift, since
-- this is naturally expressed as SQL over an already-aggregated result.
WITH monthly AS (
    SELECT
        strftime(order_purchase_timestamp, '%Y-%m') AS month,
        SUM(item_revenue) AS revenue
    FROM orders_analytics
    WHERE is_delivered
    GROUP BY month
)
SELECT
    month,
    revenue,
    LAG(revenue) OVER (ORDER BY month) AS prev_month_revenue,
    ROUND(
        100.0 * (revenue - LAG(revenue) OVER (ORDER BY month))
        / NULLIF(LAG(revenue) OVER (ORDER BY month), 0),
        1
    ) AS mom_growth_pct
FROM monthly
ORDER BY month;

-- 4. Revenue by product category (item grain -> aggregated) --------------
-- order_items_analytics is item grain, so an order with 3 categories
-- contributes to 3 category rows here — category order_count values must
-- never be summed and reported as "total orders".
SELECT
    product_category_english,
    SUM(price)                       AS revenue,
    COUNT(*)                         AS item_count,
    COUNT(DISTINCT order_id)         AS order_count,
    ROUND(AVG(price), 2)             AS avg_item_price,
    ROUND(100.0 * SUM(price) / SUM(SUM(price)) OVER (), 2) AS pct_of_total_revenue
FROM order_items_analytics
WHERE is_delivered
GROUP BY product_category_english
ORDER BY revenue DESC
LIMIT 15;

-- 5. Revenue by customer state ---------------------------------------------
SELECT
    customer_state,
    SUM(item_revenue)                            AS revenue,
    COUNT(DISTINCT order_id)                     AS orders,
    COUNT(DISTINCT customer_unique_id)            AS customers,
    ROUND(SUM(item_revenue) / COUNT(DISTINCT order_id), 2) AS aov
FROM orders_analytics
WHERE is_delivered
GROUP BY customer_state
ORDER BY revenue DESC;
