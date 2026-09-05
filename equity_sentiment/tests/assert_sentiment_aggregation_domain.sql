SELECT
    ticker,
    date_t,
    weighted_sentiment,
    news_count,
    total_relevance,
    log_news_count
FROM {{ ref('int_daily_sentiment') }}
WHERE weighted_sentiment IS NULL
   OR weighted_sentiment NOT BETWEEN -1 AND 1
   OR news_count < 1
   OR total_relevance <= 0
   OR ABS(log_news_count - LN(news_count + 1)) > 1e-12
