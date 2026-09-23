-- Customer segmentation
-- Traditional RFM was evaluated and rejected for this dataset: 97.0% of
-- customers have Frequency = 1, leaving no meaningful variation to build a
-- Frequency quintile from (see README.md, "Customer Retention &
-- Segmentation"). This file instead demonstrates the RFM-suitability
-- evidence directly in SQL, then builds the behavior-based segmentation
-- used instead (src/segmentation.py::assign_customer_segment).

-- 1. Why RFM doesn't fit: frequency distribution ---------------------------
WITH customer_orders AS (
    SELECT customer_unique_id, COUNT(DISTINCT order_id) AS delivered_order_count
    FROM orders_analytics
    WHERE is_delivered
    GROUP BY customer_unique_id
)
SELECT
    delivered_order_count,
    COUNT(*)                                          AS customers,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_customers
FROM customer_orders
GROUP BY delivered_order_count
ORDER BY delivered_order_count;

-- 2. Why RFM doesn't fit: monetary value is heavily right-skewed -----------
WITH customer_revenue AS (
    SELECT customer_unique_id, SUM(item_revenue) AS total_revenue
    FROM orders_analytics
    WHERE is_delivered
    GROUP BY customer_unique_id
)
SELECT
    ROUND(MEDIAN(total_revenue), 2)                  AS median_revenue,
    ROUND(AVG(total_revenue), 2)                     AS mean_revenue,
    ROUND(QUANTILE_CONT(total_revenue, 0.75), 2)      AS p75_revenue,
    ROUND(QUANTILE_CONT(total_revenue, 0.90), 2)      AS p90_revenue,
    ROUND(MAX(total_revenue), 2)                      AS max_revenue
FROM customer_revenue;

-- 3. Segmentation ------------------------------------------------------------
-- Mirrors src/segmentation.py::assign_customer_segment: repeat status is
-- checked first (the strongest behavioral signal), then whether revenue is
-- in the top quartile ("high value"), then — for one-time customers only —
-- whether the (only) purchase was within the last 90 days.
WITH census AS (
    SELECT MAX(order_purchase_timestamp) AS census_date FROM orders_analytics WHERE is_delivered
),
customer_summary AS (
    SELECT
        customer_unique_id,
        COUNT(DISTINCT order_id)                                   AS delivered_order_count,
        SUM(item_revenue)                                          AS total_revenue,
        -- FLOOR(seconds / 86400) = exact elapsed days, matching pandas
        -- Timedelta.days — see README.md, "Cross-Language Consistency"
        FLOOR(DATE_DIFF('second', MAX(order_purchase_timestamp), (SELECT census_date FROM census)) / 86400.0) AS recency_days
    FROM orders_analytics
    WHERE is_delivered
    GROUP BY customer_unique_id
),
thresholds AS (
    SELECT QUANTILE_CONT(total_revenue, 0.75) AS value_threshold FROM customer_summary
),
segmented AS (
    SELECT
        c.*,
        CASE
            WHEN delivered_order_count >= 2 AND total_revenue > t.value_threshold THEN 'High-Value Repeat'
            WHEN delivered_order_count >= 2 THEN 'Repeat Customer'
            WHEN total_revenue > t.value_threshold THEN 'High-Value One-Time'
            WHEN recency_days <= 90 THEN 'One-Time Recent'
            ELSE 'One-Time Lapsed'
        END AS segment
    FROM customer_summary c, thresholds t
)
SELECT
    segment,
    COUNT(*)                AS customers,
    ROUND(SUM(total_revenue), 2)  AS total_revenue,
    ROUND(AVG(total_revenue), 2)  AS avg_revenue_per_customer,
    ROUND(100.0 * SUM(total_revenue) / SUM(SUM(total_revenue)) OVER (), 2) AS pct_of_revenue
FROM segmented
GROUP BY segment
ORDER BY total_revenue DESC;
