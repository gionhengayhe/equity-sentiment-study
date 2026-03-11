WITH base AS (

    SELECT
        p.date_t,
        p.ticker,
        p.sentiment_quintile,
        p.forward_return_1d,
        p.dollar_volume
    FROM {{ ref('fct_signal_panel') }} p
    WHERE p.sentiment_quintile IS NOT NULL
        AND p.date_t IN (
            SELECT full_date
            FROM {{ ref('dim_date') }}
            WHERE trading_day_flag = 1
        )

),

-- Total universe from price (before sentiment filter)
daily_universe AS (

    SELECT
        date_t,
        COUNT(DISTINCT ticker) AS total_stocks
    FROM {{ ref('int_price_features') }}
    GROUP BY date_t

),

universe AS (
    SELECT
        COUNT(DISTINCT ticker) AS total_universe_stocks
    FROM {{ ref('stg_companies') }}
),

aggregated AS (

    SELECT
        date_t,

        -- Equal-weighted returns
        AVG(CASE WHEN sentiment_quintile = 5 THEN forward_return_1d END)    AS q5_return,
        AVG(CASE WHEN sentiment_quintile = 1 THEN forward_return_1d END)    AS q1_return,

        -- Quintile counts
        COUNT(CASE WHEN sentiment_quintile = 5 THEN 1 END)                  AS q5_count,
        COUNT(CASE WHEN sentiment_quintile = 1 THEN 1 END)                  AS q1_count,

        -- Stocks with signal (numerator for coverage)
        COUNT(DISTINCT ticker)                                              AS stocks_with_signal

    FROM base
    GROUP BY date_t

),

vw_aggregated AS (

    SELECT
        date_t,

        SUM(CASE WHEN sentiment_quintile = 5
                 THEN forward_return_1d * dollar_volume END)
        / NULLIF(SUM(CASE WHEN sentiment_quintile = 5
                          THEN dollar_volume END), 0)                       AS q5_return_vw,

        SUM(CASE WHEN sentiment_quintile = 1
                 THEN forward_return_1d * dollar_volume END)
        / NULLIF(SUM(CASE WHEN sentiment_quintile = 1
                          THEN dollar_volume END), 0)                       AS q1_return_vw

    FROM base
    GROUP BY date_t

)

SELECT
    a.date_t,

    -- Equal-weighted
    a.q5_return as q5_return_ew,
    a.q1_return as q1_return_ew,
    a.q5_return - a.q1_return                                              AS spread_ew,

    -- Value-weighted
    v.q5_return_vw,
    v.q1_return_vw,
    v.q5_return_vw - v.q1_return_vw                                        AS spread_vw,

    -- Diagnostics
    a.q5_count,
    a.q1_count,

    -- Coverage
    a.stocks_with_signal,
    u.total_stocks,
    un.total_universe_stocks - u.total_stocks                             AS missing_price_count,
    a.stocks_with_signal::FLOAT / NULLIF(u.total_stocks, 0)               AS coverage_ratio

FROM aggregated a
LEFT JOIN vw_aggregated v ON a.date_t = v.date_t
LEFT JOIN daily_universe u ON a.date_t = u.date_t
CROSS JOIN universe un

ORDER BY a.date_t