SELECT
    news_id,
    ticker,
    published_at,
    date_t
FROM {{ ref('stg_news') }}
WHERE published_at IS NULL
   OR date_t IS NULL
   OR date_t < CAST(published_at AS DATE)
   OR (
        CAST(published_at AS TIME) >= TIME '16:00:00'
        AND date_t <= CAST(published_at AS DATE)
   )
