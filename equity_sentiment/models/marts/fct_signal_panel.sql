WITH company_metadata AS (
    -- Current metadata is optional enrichment only. Collapsing to one row per
    -- ticker prevents a current-company dimension issue from multiplying facts.
    SELECT
        ticker,
        ANY_VALUE(name) AS name,
        ANY_VALUE(sector) AS sector,
        ANY_VALUE(industry) AS industry,
        ANY_VALUE(sic) AS sic
    FROM {{ ref('stg_companies') }}
    GROUP BY ticker
),

base AS (
    SELECT
        p.ticker,
        -- date_t is the canonical signal formation date at the 16:00 ET close.
        p.date_t,

        -- Price features
        p.close,
        p.volume,
        p.next_trading_date,
        p.close_to_close_return_1d,
        p.log_close_to_close_return_1d,
        p.forward_return_close_to_close_1d,

        -- Sentiment features
        coalesce(s.weighted_sentiment, 0) AS weighted_sentiment,
        CASE 
            WHEN s.weighted_sentiment IS NULL THEN 0
            ELSE 1
        END AS has_sentiment_flag,
        s.news_count,
        s.total_relevance,
        s.log_news_count,

        -- Current company metadata; never used as an eligibility filter.
        c.name,
        c.sector,
        c.industry,
        c.sic,
        CASE WHEN c.ticker IS NOT NULL THEN 1 ELSE 0 END
            AS company_metadata_available_flag

    FROM {{ ref('int_price_features') }} p
    LEFT JOIN {{ ref('int_daily_sentiment') }} s
        ON p.ticker = s.ticker
        AND p.date_t = s.date_t
    LEFT JOIN company_metadata c
        ON p.ticker = c.ticker

),

-- 1️⃣ Cross-sectional daily statistics
daily_stats AS (
    SELECT
        *,
        AVG(weighted_sentiment)
            OVER (PARTITION BY date_t) AS daily_mean_sentiment,

        STDDEV_SAMP(weighted_sentiment)
            OVER (PARTITION BY date_t) AS daily_std_sentiment
    FROM base
    WHERE has_sentiment_flag = 1 and news_count > 1

),

-- 2️⃣ Z-score computation
z_scored AS (
    SELECT
        *,
        CASE
            WHEN daily_std_sentiment IS NOT NULL
                 AND daily_std_sentiment != 0
            THEN (weighted_sentiment - daily_mean_sentiment)
                 / daily_std_sentiment
            ELSE 0
        END AS z_sentiment
    FROM daily_stats
),

-- 3️⃣ Daily cross-sectional quintiles (based on z_sentiment)
ranked AS (
    SELECT
        *,
        NTILE(5) OVER (
            PARTITION BY date_t
            ORDER BY z_sentiment
        ) AS sentiment_quintile
    FROM z_scored
)

SELECT
    -- Keys (for star schema)
    ticker,
    date_t,

    -- Price
    close,
    volume,
    next_trading_date,
    close_to_close_return_1d,
    log_close_to_close_return_1d,
    forward_return_close_to_close_1d,

    -- Backward-compatible aliases for the existing Power BI model.
    close_to_close_return_1d AS return_1d,
    log_close_to_close_return_1d AS log_return_1d,
    forward_return_close_to_close_1d AS forward_return_1d,

    -- Sentiment
    weighted_sentiment,
    has_sentiment_flag,
    z_sentiment,
    sentiment_quintile,
    news_count,
    total_relevance,
    log_news_count,

    -- Company
    name,
    sector,
    industry,
    sic,
    company_metadata_available_flag,
    1 AS point_in_time_universe_flag,

    -- Useful derived fields for dashboard slicing
    volume * close AS dollar_volume,
    LOG(volume * close) AS log_dollar_volume,

    CASE
        WHEN volume * close IS NULL THEN 'Unknown'
        WHEN volume * close < 1e6 THEN 'Low Liquidity'
        WHEN volume * close < 1e7 THEN 'Mid Liquidity'
        ELSE 'High Liquidity'
    END AS liquidity_bucket,

    CASE 
        WHEN news_count = 2 or news_count = 3 THEN '2-3'
        WHEN news_count = 4 or news_count = 5 THEN '4-5'
        ELSE '5+'
    END AS news_count_bucket
FROM ranked
