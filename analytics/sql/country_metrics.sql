-- Daily metrics per country: geographic performance.
--
-- Rows with no country are grouped under 'unknown' rather than dropped.
-- Silently discarding them would make the country totals disagree with the
-- overall review count, and someone would eventually have to work out why.
SELECT
    review_date,
    COALESCE(NULLIF(TRIM(country), ''), 'unknown')             AS country,
    COUNT(*)                                                   AS review_count,
    ROUND(AVG(CAST(rating AS DOUBLE)), 3)                      AS average_rating,
    SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END)    AS negative_count,
    ROUND(100.0 * SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) / COUNT(*), 2)
                                                               AS negative_percentage,
    COUNT(DISTINCT brand)                                      AS brand_count
FROM silver
WHERE is_duplicate_of IS NULL
GROUP BY review_date, COALESCE(NULLIF(TRIM(country), ''), 'unknown')
ORDER BY review_date, country
