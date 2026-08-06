-- Sentiment over time per brand, with a rolling baseline.
--
-- The 7-day rolling average is what makes a trend readable: daily sentiment on
-- a small brand swings wildly on volume alone, and a chart of raw daily values
-- shows noise rather than direction.
--
-- `ROWS BETWEEN 6 PRECEDING AND CURRENT ROW` is a trailing window -- it never
-- looks into the future. A centred window would leak tomorrow's data into
-- today's baseline and make anomaly detection quietly circular.
WITH daily AS (
    SELECT
        review_date,
        brand,
        COUNT(*)                                                AS review_count,
        SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) AS negative_count,
        ROUND(AVG(CAST(sentiment_score AS DOUBLE)), 4)          AS average_sentiment_score,
        ROUND(AVG(CAST(rating AS DOUBLE)), 3)                   AS average_rating
    FROM silver
    WHERE is_duplicate_of IS NULL
    GROUP BY review_date, brand
)
SELECT
    review_date,
    brand,
    review_count,
    negative_count,
    average_sentiment_score,
    average_rating,
    ROUND(100.0 * negative_count / review_count, 2)             AS negative_percentage,
    ROUND(AVG(100.0 * negative_count / review_count) OVER (
        PARTITION BY brand ORDER BY review_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 2)                                                       AS negative_percentage_7d,
    ROUND(AVG(CAST(review_count AS DOUBLE)) OVER (
        PARTITION BY brand ORDER BY review_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 2)                                                       AS review_count_7d
FROM daily
ORDER BY brand, review_date
