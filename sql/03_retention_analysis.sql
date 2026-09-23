-- Retention analysis
-- Repeat Customer Rate = (customers with >= 2 delivered orders)
--                         / (customers with >= 1 delivered order)
-- Computed independently in SQL here to cross-validate against the Python
-- implementation in src/metrics.py::repeat_customer_rate.

-- 1. Repeat customer rate --------------------------------------------------
WITH orders_per_customer AS (
    SELECT customer_unique_id, COUNT(DISTINCT order_id) AS delivered_order_count
    FROM orders_analytics
    WHERE is_delivered
    GROUP BY customer_unique_id
)
SELECT
    COUNT(*) FILTER (WHERE delivered_order_count >= 1) AS customers_with_1plus,
    COUNT(*) FILTER (WHERE delivered_order_count >= 2) AS customers_with_2plus,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE delivered_order_count >= 2)
        / COUNT(*) FILTER (WHERE delivered_order_count >= 1),
        2
    ) AS repeat_customer_rate_pct
FROM orders_per_customer;

-- 2. Revenue contribution: single-purchase vs repeat customers -------------
WITH orders_per_customer AS (
    SELECT customer_unique_id, COUNT(DISTINCT order_id) AS delivered_order_count,
           SUM(item_revenue) AS customer_revenue
    FROM orders_analytics
    WHERE is_delivered
    GROUP BY customer_unique_id
)
SELECT
    CASE WHEN delivered_order_count = 1 THEN 'single-purchase' ELSE 'repeat' END AS customer_type,
    COUNT(*)                                     AS customers,
    SUM(customer_revenue)                        AS revenue,
    ROUND(100.0 * SUM(customer_revenue) / SUM(SUM(customer_revenue)) OVER (), 2) AS pct_of_revenue
FROM orders_per_customer
GROUP BY customer_type;

-- 3. Time between first and second delivered order, for repeat customers ---
-- Uses ROW_NUMBER to rank each customer's delivered orders chronologically,
-- then self-joins order 1 to order 2 — a genuine use of window functions
-- that would be awkward to express as a simple pandas groupby.
WITH ranked_orders AS (
    SELECT
        customer_unique_id,
        order_id,
        order_purchase_timestamp,
        ROW_NUMBER() OVER (
            PARTITION BY customer_unique_id ORDER BY order_purchase_timestamp
        ) AS purchase_rank
    FROM orders_analytics
    WHERE is_delivered
),
first_two AS (
    SELECT
        a.customer_unique_id,
        a.order_purchase_timestamp AS first_order_ts,
        b.order_purchase_timestamp AS second_order_ts
    FROM ranked_orders a
    JOIN ranked_orders b
        ON a.customer_unique_id = b.customer_unique_id
        AND a.purchase_rank = 1
        AND b.purchase_rank = 2
)
SELECT
    COUNT(*)                                                   AS repeat_customers,
    -- FLOOR(seconds / 86400) matches pandas Timedelta.days (floor of exact
    -- elapsed time). DATE_DIFF('day', ...) instead counts calendar-date
    -- boundaries crossed, and DuckDB's CAST(...AS INTEGER) rounds rather than
    -- truncates — both would silently disagree with pandas here (see
    -- README.md, "Cross-Language Consistency").
    ROUND(AVG(FLOOR(DATE_DIFF('second', first_order_ts, second_order_ts) / 86400.0)), 1) AS avg_days_to_second_order,
    ROUND(MEDIAN(FLOOR(DATE_DIFF('second', first_order_ts, second_order_ts) / 86400.0)), 1) AS median_days_to_second_order
FROM first_two;
