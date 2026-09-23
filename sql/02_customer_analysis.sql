-- Customer analysis
-- Uses customer_unique_id throughout — customer_id is minted per order in
-- the raw data and is not a valid key for anything at the person level.
-- Population: delivered orders only.

-- 1. Unique customers and purchase-frequency distribution ------------------
WITH orders_per_customer AS (
    SELECT
        customer_unique_id,
        COUNT(DISTINCT order_id) AS delivered_order_count,
        SUM(item_revenue)        AS customer_revenue
    FROM orders_analytics
    WHERE is_delivered
    GROUP BY customer_unique_id
)
SELECT
    delivered_order_count,
    COUNT(*)                                       AS customers,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_customers
FROM orders_per_customer
GROUP BY delivered_order_count
ORDER BY delivered_order_count;

-- 2. Average revenue per customer ------------------------------------------
WITH orders_per_customer AS (
    SELECT customer_unique_id, SUM(item_revenue) AS customer_revenue
    FROM orders_analytics
    WHERE is_delivered
    GROUP BY customer_unique_id
)
SELECT
    COUNT(*)                       AS unique_customers,
    ROUND(AVG(customer_revenue), 2) AS avg_revenue_per_customer,
    ROUND(MEDIAN(customer_revenue), 2) AS median_revenue_per_customer
FROM orders_per_customer;

-- 3. Customers and AOV by state --------------------------------------------
-- Small-sample caution: states below ~100 delivered orders (see query 4 in
-- 04_delivery_analysis.sql) should not be compared to SP/RJ/MG on averages
-- without noting the sample size.
SELECT
    customer_state,
    COUNT(DISTINCT customer_unique_id)            AS customers,
    COUNT(DISTINCT order_id)                       AS orders,
    ROUND(SUM(item_revenue) / COUNT(DISTINCT order_id), 2) AS aov
FROM orders_analytics
WHERE is_delivered
GROUP BY customer_state
ORDER BY customers DESC;
