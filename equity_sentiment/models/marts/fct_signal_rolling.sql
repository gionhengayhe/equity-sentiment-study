WITH base AS (
    SELECT
        date_t,
        spread_ew,

        AVG(spread_ew) OVER (
            ORDER BY date_t
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS spread_mean_20d,

        STDDEV(spread_ew) OVER (
            ORDER BY date_t
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS spread_std_20d,

        COUNT(spread_ew) OVER (
            ORDER BY date_t
            ROWS BETWEEN 19 PRECEDING AND CURRENT ROW
        ) AS window_n

    FROM {{ ref('fct_signal_daily') }}
)

SELECT
    date_t,
    spread_ew,
    spread_mean_20d,
    spread_std_20d,
    window_n,

    CASE
        WHEN window_n >= 20
        THEN spread_mean_20d / (spread_std_20d / SQRT(window_n))
    END AS t_stat_20d

FROM base
WHERE window_n >= 20