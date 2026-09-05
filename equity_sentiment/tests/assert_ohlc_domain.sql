SELECT
    ticker,
    date_t,
    open,
    high,
    low,
    close,
    volume
FROM {{ ref('stg_ohlcs') }}
WHERE ticker IS NULL
   OR date_t IS NULL
   OR open <= 0
   OR high <= 0
   OR low <= 0
   OR close <= 0
   OR volume < 0
   OR high < GREATEST(open, close, low)
   OR low > LEAST(open, close, high)
