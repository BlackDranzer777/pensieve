-- Daily metrics per brand: the backbone of the Brand Comparison page.
--
-- Duplicates are excluded from every count. `is_duplicate_of` marks a review
-- whose text already appeared for the same brand, so counting it again would
-- inflate volume and skew the sentiment mix. The review still exists in Silver
-- and still appears in the Review Explorer -- it just does not vote twice.
--
-- Engine-agnostic: this runs unchanged on Spark SQL and DuckDB.
SELECT
    review_date,
    brand,
    COUNT(*)                                                   AS review_count,
    ROUND(AVG(CAST(rating AS DOUBLE)), 3)                      AS average_rating,
    SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END)    AS positive_count,
    SUM(CASE WHEN sentiment = 'neutral'  THEN 1 ELSE 0 END)    AS neutral_count,
    SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END)    AS negative_count,
    ROUND(100.0 * SUM(CASE WHEN sentiment = 'positive' THEN 1 ELSE 0 END) / COUNT(*), 2)
                                                               AS positive_percentage,
    ROUND(100.0 * SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) / COUNT(*), 2)
                                                               AS negative_percentage,
    ROUND(AVG(CAST(sentiment_score AS DOUBLE)), 4)             AS average_sentiment_score,
    COUNT(DISTINCT country)                                    AS country_count,
    COUNT(DISTINCT language)                                   AS language_count
FROM silver
WHERE is_duplicate_of IS NULL
GROUP BY review_date, brand
ORDER BY review_date, brand
