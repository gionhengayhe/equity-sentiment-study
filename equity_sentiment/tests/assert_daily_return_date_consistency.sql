SELECT
    date_t,
    return_date_t,
    latest_return_date_t
FROM {{ ref('fct_signal_daily') }}
WHERE return_date_t IS NULL
   OR return_date_t <= date_t
   OR return_date_t IS DISTINCT FROM latest_return_date_t
