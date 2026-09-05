WITH base AS (
    SELECT
        date_t,
        long_short_return_ew,

        AVG(long_short_return_ew) OVER (
            ORDER BY date_t
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS long_short_mean_20d,

        STDDEV(long_short_return_ew) OVER (
            ORDER BY date_t
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS long_short_std_20d,

        COUNT(long_short_return_ew) OVER (
            ORDER BY date_t
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS window_n

    FROM {{ ref('fct_signal_daily') }}
)

SELECT
    date_t,
    long_short_return_ew,
    long_short_mean_20d,
    long_short_std_20d,
    window_n,

    -- Descriptive rolling t-statistic under an IID assumption.
    CASE
        WHEN window_n >= 20
        THEN long_short_mean_20d / (long_short_std_20d / SQRT(window_n))
    END AS t_stat_20d,

    -- Backward-compatible aliases for the existing dashboard.
    long_short_return_ew AS spread_ew,
    long_short_mean_20d AS spread_mean_20d,
    long_short_std_20d AS spread_std_20d

FROM base
WHERE window_n >= 20
