WITH base AS (
    SELECT
        p.date_t,
        p.ticker,
        p.sentiment_quintile,
        p.next_trading_date,
        p.forward_return_close_to_close_1d,
        p.dollar_volume
    FROM {{ ref('fct_signal_panel') }} p
    WHERE p.sentiment_quintile IS NOT NULL
        AND p.forward_return_close_to_close_1d IS NOT NULL
),

-- Total price universe before the sentiment eligibility filter.
daily_universe AS (
    SELECT
        p.date_t,
        COUNT(DISTINCT p.ticker) AS total_stocks,
        COUNT(DISTINCT CASE WHEN c.ticker IS NULL THEN p.ticker END)
            AS stocks_without_current_metadata
    FROM {{ ref('int_price_features') }} p
    LEFT JOIN {{ ref('stg_companies') }} c
        ON p.ticker = c.ticker
    WHERE p.forward_return_close_to_close_1d IS NOT NULL
    GROUP BY p.date_t
),

aggregated AS (
    SELECT
        date_t,
        MIN(next_trading_date) AS return_date_t,
        MAX(next_trading_date) AS latest_return_date_t,

        -- Each leg invests one unit of capital. Q5 - Q1 therefore has
        -- 200% gross exposure and 0% net exposure.
        AVG(CASE WHEN sentiment_quintile = 5
                 THEN forward_return_close_to_close_1d END) AS q5_return_ew,
        AVG(CASE WHEN sentiment_quintile = 1
                 THEN forward_return_close_to_close_1d END) AS q1_return_ew,

        COUNT(CASE WHEN sentiment_quintile = 5 THEN 1 END) AS q5_count,
        COUNT(CASE WHEN sentiment_quintile = 1 THEN 1 END) AS q1_count,
        COUNT(DISTINCT ticker) AS stocks_with_signal
    FROM base
    GROUP BY date_t
),

liquidity_weighted AS (
    SELECT
        date_t,
        SUM(CASE WHEN sentiment_quintile = 5
                 THEN forward_return_close_to_close_1d * dollar_volume END)
        / NULLIF(SUM(CASE WHEN sentiment_quintile = 5
                          THEN dollar_volume END), 0) AS q5_return_lw,

        SUM(CASE WHEN sentiment_quintile = 1
                 THEN forward_return_close_to_close_1d * dollar_volume END)
        / NULLIF(SUM(CASE WHEN sentiment_quintile = 1
                          THEN dollar_volume END), 0) AS q1_return_lw
    FROM base
    GROUP BY date_t
),

daily_returns AS (
    SELECT
        a.date_t,
        a.return_date_t,
        a.latest_return_date_t,
        a.q5_return_ew,
        a.q1_return_ew,
        a.q5_return_ew - a.q1_return_ew AS long_short_return_ew,

        l.q5_return_lw,
        l.q1_return_lw,
        l.q5_return_lw - l.q1_return_lw AS long_short_return_lw,

        a.q5_count,
        a.q1_count,
        a.stocks_with_signal,
        u.total_stocks,
        u.stocks_without_current_metadata,
        a.stocks_with_signal::FLOAT / NULLIF(u.total_stocks, 0) AS coverage_ratio
    FROM aggregated a
    LEFT JOIN liquidity_weighted l ON a.date_t = l.date_t
    LEFT JOIN daily_universe u ON a.date_t = u.date_t
)

SELECT
    *,

    -- Canonical cumulative strategy return: compounded daily long-short returns.
    PRODUCT(1 + long_short_return_ew) OVER (
        ORDER BY date_t
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) - 1 AS cumulative_return_ew,

    PRODUCT(1 + long_short_return_lw) OVER (
        ORDER BY date_t
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) - 1 AS cumulative_return_lw,

    -- Arithmetic cumulative spread is retained as a research diagnostic only.
    SUM(long_short_return_ew) OVER (
        ORDER BY date_t
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_spread_ew,

    SUM(long_short_return_lw) OVER (
        ORDER BY date_t
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_spread_lw,

    2.0 AS gross_exposure,
    0.0 AS net_exposure,

    -- Backward-compatible aliases for the existing dashboard.
    q5_return_lw AS q5_return_vw,
    q1_return_lw AS q1_return_vw,
    long_short_return_ew AS spread_ew,
    long_short_return_lw AS spread_vw,
    stocks_without_current_metadata AS missing_price_count
FROM daily_returns
ORDER BY date_t
