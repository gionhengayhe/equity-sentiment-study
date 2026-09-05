SELECT *
FROM {{ ref('fct_signal_daily') }}
WHERE ABS(long_short_return_ew - (q5_return_ew - q1_return_ew)) > 1e-12
   OR ABS(long_short_return_lw - (q5_return_lw - q1_return_lw)) > 1e-12
   OR gross_exposure != 2.0
   OR net_exposure != 0.0
