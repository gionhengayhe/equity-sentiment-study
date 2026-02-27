WITH base AS (
    SELECT
        p.ticker,
        p.date_t,

        -- Price features
        p.close,
        p.volume,
        p.return_1d,
        p.log_return_1d,
        p.forward_return_1d,

        -- Sentiment features
        s.weighted_sentiment,
        s.news_count,
        s.avg_relevance,

        -- Company metadata
        c.name,
        c.sector,
        c.industry,
        c.sic

    FROM {{ ref('int_price_features') }} p
    LEFT JOIN {{ ref('int_daily_sentiment') }} s
        ON p.ticker = s.ticker
        AND p.date_t = s.date_t
    LEFT JOIN {{ ref('stg_companies') }} c
        ON p.ticker = c.ticker
)

SELECT
    *,
    
    -- Cross-sectional mean & std per day
    AVG(weighted_sentiment)
        OVER (PARTITION BY date_t) AS daily_mean_sentiment,

    STDDEV_SAMP(weighted_sentiment)
        OVER (PARTITION BY date_t) AS daily_std_sentiment,

    -- Z-score
    CASE 
        WHEN STDDEV_SAMP(weighted_sentiment)
             OVER (PARTITION BY date_t) IS NOT NULL
             AND STDDEV_SAMP(weighted_sentiment)
             OVER (PARTITION BY date_t) != 0
        THEN
            (weighted_sentiment
             - AVG(weighted_sentiment)
               OVER (PARTITION BY date_t))
            /
            STDDEV_SAMP(weighted_sentiment)
               OVER (PARTITION BY date_t)
        ELSE NULL
    END AS z_sentiment

FROM base