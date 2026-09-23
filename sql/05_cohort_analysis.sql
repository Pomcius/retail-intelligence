-- Cohort retention analysis
-- Cohort = calendar month of a customer's first delivered order.
-- period_index = number of calendar months between the cohort month and a
-- given order's purchase month (0 = the cohort month itself).
-- Population: delivered orders only. Uses customer_unique_id throughout.

-- 1. Cohort sizes -----------------------------------------------------------
WITH first_purchase AS (
    SELECT
        customer_unique_id,
        MIN(DATE_TRUNC('month', order_purchase_timestamp)) AS cohort_month
    FROM orders_analytics
    WHERE is_delivered
    GROUP BY customer_unique_id
)
SELECT
    strftime(cohort_month, '%Y-%m') AS cohort_month,
    COUNT(*)                         AS cohort_size
FROM first_purchase
GROUP BY cohort_month
ORDER BY cohort_month;

-- 2. Cohort x period_index retention counts ---------------------------------
-- This is the long-format table the Python cohort matrix (src/segmentation.py)
-- is built from — kept here so the same cohort logic is independently
-- expressible and checkable in SQL.
WITH first_purchase AS (
    SELECT
        customer_unique_id,
        DATE_TRUNC('month', MIN(order_purchase_timestamp)) AS cohort_month
    FROM orders_analytics
    WHERE is_delivered
    GROUP BY customer_unique_id
),
events AS (
    SELECT
        o.customer_unique_id,
        f.cohort_month,
        DATE_DIFF('month', f.cohort_month, DATE_TRUNC('month', o.order_purchase_timestamp)) AS period_index
    FROM orders_analytics o
    JOIN first_purchase f ON o.customer_unique_id = f.customer_unique_id
    WHERE o.is_delivered
)
SELECT
    strftime(cohort_month, '%Y-%m') AS cohort_month,
    period_index,
    COUNT(DISTINCT customer_unique_id) AS active_customers
FROM events
GROUP BY cohort_month, period_index
ORDER BY cohort_month, period_index;

-- Note: the DuckDB result above only contains rows for (cohort, period)
-- combinations with at least one active customer. A period with genuinely
-- zero returning customers, and a period that hasn't happened yet as of the
-- dataset's last observed month, both produce no row here — they must be
-- told apart using the cohort's observable range (see
-- src/segmentation.py::build_cohort_retention_matrix), not treated as
-- interchangeable "0%" outcomes.

-- 3. Repeat-purchase timing (independent of the eligibility-adjusted
--    windows in Python) ------------------------------------------------------
-- Median/quartile days between a customer's first and second delivered
-- order, among customers who actually returned.
WITH ranked AS (
    SELECT
        customer_unique_id,
        order_purchase_timestamp,
        ROW_NUMBER() OVER (PARTITION BY customer_unique_id ORDER BY order_purchase_timestamp) AS rn
    FROM orders_analytics
    WHERE is_delivered
),
first_second AS (
    SELECT
        a.customer_unique_id,
        DATE_DIFF('day', a.order_purchase_timestamp, b.order_purchase_timestamp) AS days_to_second_purchase
    FROM ranked a
    JOIN ranked b ON a.customer_unique_id = b.customer_unique_id AND a.rn = 1 AND b.rn = 2
)
SELECT
    COUNT(*)                                              AS repeat_customers,
    ROUND(MEDIAN(days_to_second_purchase), 1)              AS median_days,
    ROUND(AVG(days_to_second_purchase), 1)                 AS mean_days,
    ROUND(QUANTILE_CONT(days_to_second_purchase, 0.25), 1) AS p25_days,
    ROUND(QUANTILE_CONT(days_to_second_purchase, 0.75), 1) AS p75_days
FROM first_second;
