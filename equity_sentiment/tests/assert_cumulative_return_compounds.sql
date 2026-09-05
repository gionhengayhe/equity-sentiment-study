WITH expected AS (
    SELECT
        date_t,
        PRODUCT(1 + long_short_return_ew) OVER (
            ORDER BY date_t
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) - 1 AS expected_cumulative_return_ew,
        PRODUCT(1 + long_short_return_lw) OVER (
            ORDER BY date_t
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) - 1 AS expected_cumulative_return_lw
    FROM {{ ref('fct_signal_daily') }}
)

SELECT d.*
FROM {{ ref('fct_signal_daily') }} d
INNER JOIN expected e USING (date_t)
WHERE ABS(d.cumulative_return_ew - e.expected_cumulative_return_ew) > 1e-12
   OR ABS(d.cumulative_return_lw - e.expected_cumulative_return_lw) > 1e-12
