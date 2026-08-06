-- Daily metrics per brand and topic: answers "which complaints are growing?"
--
-- `other` is included rather than filtered out. A rising share of `other` is
-- itself a finding -- it means customers are discussing something the topic
-- taxonomy does not yet cover.
SELECT
    review_date,
    brand,
    primary_topic                                              AS topic,
    COUNT(*)                                                   AS review_count,
    ROUND(AVG(CAST(rating AS DOUBLE)), 3)                      AS average_rating,
    SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END)    AS negative_count,
    ROUND(100.0 * SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END) / COUNT(*), 2)
                                                               AS negative_percentage,
    ROUND(AVG(CAST(sentiment_score AS DOUBLE)), 4)             AS average_sentiment_score
FROM silver
WHERE is_duplicate_of IS NULL
GROUP BY review_date, brand, primary_topic
ORDER BY review_date, brand, primary_topic
