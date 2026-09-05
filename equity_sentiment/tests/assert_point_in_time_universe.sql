WITH expected AS (
    SELECT
        prices.ticker,
        prices.date_t
    FROM {{ ref('int_price_features') }} prices
    INNER JOIN {{ ref('int_daily_sentiment') }} sentiment
        ON prices.ticker = sentiment.ticker
       AND prices.date_t = sentiment.date_t
    WHERE sentiment.news_count > 1
),

missing_from_panel AS (
    SELECT * FROM expected
    EXCEPT
    SELECT ticker, date_t FROM {{ ref('fct_signal_panel') }}
),

unexpected_in_panel AS (
    SELECT ticker, date_t FROM {{ ref('fct_signal_panel') }}
    EXCEPT
    SELECT * FROM expected
)

SELECT * FROM missing_from_panel
UNION ALL
SELECT * FROM unexpected_in_panel
