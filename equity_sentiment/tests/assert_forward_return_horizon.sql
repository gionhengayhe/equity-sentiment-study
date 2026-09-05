WITH market_dates AS (
    SELECT DISTINCT date_t
    FROM {{ ref('stg_ohlcs') }}
),

market_calendar AS (
    SELECT
        date_t,
        LEAD(date_t) OVER (ORDER BY date_t) AS expected_next_trading_date
    FROM market_dates
),

expected AS (
    SELECT
        current_price.ticker,
        current_price.date_t,
        calendar.expected_next_trading_date,
        (next_price.close / NULLIF(current_price.close, 0)) - 1
            AS expected_forward_return
    FROM {{ ref('stg_ohlcs') }} current_price
    INNER JOIN market_calendar calendar
        ON current_price.date_t = calendar.date_t
    LEFT JOIN {{ ref('stg_ohlcs') }} next_price
        ON current_price.ticker = next_price.ticker
       AND calendar.expected_next_trading_date = next_price.date_t
)

SELECT
    actual.ticker,
    actual.date_t,
    expected.expected_next_trading_date,
    actual.next_trading_date AS modeled_next_trading_date,
    actual.forward_return_close_to_close_1d,
    expected.expected_forward_return
FROM {{ ref('int_price_features') }} actual
INNER JOIN expected
    ON actual.ticker = expected.ticker
   AND actual.date_t = expected.date_t
WHERE actual.next_trading_date IS DISTINCT FROM expected.expected_next_trading_date
   OR (actual.forward_return_close_to_close_1d IS NULL)
      != (expected.expected_forward_return IS NULL)
   OR (
        actual.forward_return_close_to_close_1d IS NOT NULL
        AND expected.expected_forward_return IS NOT NULL
        AND ABS(
            actual.forward_return_close_to_close_1d
            - expected.expected_forward_return
        ) > 1e-12
   )
