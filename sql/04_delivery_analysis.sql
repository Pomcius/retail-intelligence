-- Delivery and review analysis
-- Timing-eligible population: delivered orders where an actual customer
-- delivery date exists (excludes a small number of 'delivered' orders with
-- a missing delivery timestamp — a data anomaly, not a business outcome).
-- Delivery delay = actual delivery date - estimated delivery date;
-- positive = late.

-- 1. On-time / late delivery rate ------------------------------------------
SELECT
    COUNT(*)                                              AS timing_eligible_orders,
    COUNT(*) FILTER (WHERE delivery_delay_days <= 0)      AS on_time_orders,
    COUNT(*) FILTER (WHERE delivery_delay_days > 0)        AS late_orders,
    ROUND(100.0 * COUNT(*) FILTER (WHERE delivery_delay_days <= 0) / COUNT(*), 2) AS on_time_rate_pct,
    ROUND(100.0 * COUNT(*) FILTER (WHERE delivery_delay_days > 0) / COUNT(*), 2)  AS late_rate_pct,
    ROUND(AVG(delivery_days), 2)                          AS avg_delivery_days,
    ROUND(MEDIAN(delivery_days), 2)                       AS median_delivery_days
FROM orders_analytics
WHERE is_delivered AND delivery_delay_days IS NOT NULL;

-- 2. Review score by delivery-delay bucket ----------------------------------
-- The key business question: are late deliveries associated with worse
-- reviews? (Association only — this is observational data, not an
-- experiment, so no causal claim is made.)
SELECT
    CASE
        WHEN delivery_delay_days < -7 THEN '1. early by >7 days'
        WHEN delivery_delay_days <= 0 THEN '2. on-time / early (<=7 days early)'
        WHEN delivery_delay_days <= 3 THEN '3. 1-3 days late'
        WHEN delivery_delay_days <= 7 THEN '4. 4-7 days late'
        ELSE '5. 8+ days late'
    END AS delay_bucket,
    COUNT(*)                          AS orders,
    ROUND(AVG(avg_review_score), 3)   AS avg_review_score
FROM orders_analytics
WHERE is_delivered AND delivery_delay_days IS NOT NULL
GROUP BY delay_bucket
ORDER BY delay_bucket;

-- 3. Delivery performance by customer state ----------------------------------
-- States with very few timing-eligible orders are noted separately (see the
-- `n` column) rather than being ranked alongside high-volume states.
SELECT
    customer_state,
    COUNT(*)                                          AS timing_eligible_orders,
    ROUND(100.0 * COUNT(*) FILTER (WHERE delivery_delay_days <= 0) / COUNT(*), 2) AS on_time_rate_pct,
    ROUND(AVG(delivery_days), 1)                       AS avg_delivery_days,
    ROUND(AVG(avg_review_score), 3)                    AS avg_review_score
FROM orders_analytics
WHERE is_delivered AND delivery_delay_days IS NOT NULL
GROUP BY customer_state
ORDER BY timing_eligible_orders DESC;
