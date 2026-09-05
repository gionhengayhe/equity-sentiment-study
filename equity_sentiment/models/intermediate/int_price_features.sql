WITH market_dates AS (
    SELECT DISTINCT date_t
    FROM {{ ref('stg_ohlcs') }}
),

market_calendar AS (
    SELECT
        date_t,
        LAG(date_t) OVER (ORDER BY date_t) AS previous_trading_date,
        LEAD(date_t) OVER (ORDER BY date_t) AS next_trading_date
    FROM market_dates
),

aligned_prices AS (
    SELECT
        current_price.ticker,
        current_price.date_t,
        current_price.close,
        current_price.volume,
        calendar.previous_trading_date,
        calendar.next_trading_date,
        previous_price.close AS previous_close,
        next_price.close AS next_close
    FROM {{ ref('stg_ohlcs') }} current_price
    INNER JOIN market_calendar calendar
        ON current_price.date_t = calendar.date_t
    LEFT JOIN {{ ref('stg_ohlcs') }} previous_price
        ON current_price.ticker = previous_price.ticker
       AND calendar.previous_trading_date = previous_price.date_t
    LEFT JOIN {{ ref('stg_ohlcs') }} next_price
        ON current_price.ticker = next_price.ticker
       AND calendar.next_trading_date = next_price.date_t
),

returns AS (
    SELECT
        ticker,
        date_t,
        close,
        volume,
        previous_trading_date,
        next_trading_date,
        (close / NULLIF(previous_close, 0)) - 1 AS close_to_close_return_1d,
        LN(close / NULLIF(previous_close, 0)) AS log_close_to_close_return_1d,
        (next_close / NULLIF(close, 0)) - 1 AS forward_return_close_to_close_1d
    FROM aligned_prices
)

SELECT
    ticker,
    date_t,
    close,
    volume,
    previous_trading_date,
    next_trading_date,
    close_to_close_return_1d,
    log_close_to_close_return_1d,
    forward_return_close_to_close_1d,

    -- Backward-compatible aliases. New analysis should use the explicit names above.
    close_to_close_return_1d AS return_1d,
    log_close_to_close_return_1d AS log_return_1d,
    forward_return_close_to_close_1d AS forward_return_1d
FROM returns
