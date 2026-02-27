WITH lagged AS (
    SELECT
        ticker,
        date_t,
        close,
        volume,
        LAG(close) OVER (PARTITION BY ticker ORDER BY date_t)  AS prev_close,
        LEAD(close) OVER (PARTITION BY ticker ORDER BY date_t) AS next_close
    FROM {{ ref('stg_ohlcs') }}
)
SELECT
    ticker,
    date_t,
    close,
    volume,
    -- Daily return (contemporaneous, for context only)
    (close / NULLIF(prev_close, 0)) - 1                        AS return_1d,
    -- Log return
    LN(close / NULLIF(prev_close, 0))                          AS log_return_1d,
    -- Forward return (this is your target variable)
    (next_close / NULLIF(close, 0)) - 1                        AS forward_return_1d
FROM lagged
