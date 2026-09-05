SELECT
    date_t,
    q5_count,
    q1_count,
    stocks_with_signal,
    total_stocks,
    coverage_ratio
FROM {{ ref('fct_signal_daily') }}
WHERE q5_count < 1
   OR q1_count < 1
   OR stocks_with_signal < q5_count + q1_count
   OR total_stocks < stocks_with_signal
   OR coverage_ratio NOT BETWEEN 0 AND 1
