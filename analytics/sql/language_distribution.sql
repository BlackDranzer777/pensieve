-- Daily language mix, and the health of language detection itself.
--
-- `unknown` and `unsupported` are kept as first-class rows. They are the
-- detection-quality signal: a rising `unknown` share means text is arriving
-- too short or too noisy to classify, and a rising `unsupported` share means
-- a market worth supporting is growing.
SELECT
    review_date,
    language,
    COUNT(*)                                                   AS review_count,
    ROUND(AVG(CAST(language_confidence AS DOUBLE)), 4)         AS average_confidence,
    SUM(CASE WHEN sentiment = 'negative' THEN 1 ELSE 0 END)    AS negative_count,
    ROUND(AVG(CAST(rating AS DOUBLE)), 3)                      AS average_rating
FROM silver
WHERE is_duplicate_of IS NULL
GROUP BY review_date, language
ORDER BY review_date, language
