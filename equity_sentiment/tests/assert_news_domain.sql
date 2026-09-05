SELECT
    news_id,
    ticker,
    published_at,
    date_t,
    sentiment_score,
    relevance_score
FROM {{ ref('stg_news') }}
WHERE news_id IS NULL
   OR ticker IS NULL
   OR published_at IS NULL
   OR date_t IS NULL
   OR sentiment_score NOT BETWEEN -1 AND 1
   OR relevance_score NOT BETWEEN 0.5 AND 1
   OR date_t < CAST(published_at AS DATE)
