WITH duplicate_grains AS (
    SELECT
        'stg_ohlcs' AS model_name,
        ticker AS key_1,
        CAST(date_t AS VARCHAR) AS key_2,
        COUNT(*) AS duplicate_count
    FROM {{ ref('stg_ohlcs') }}
    GROUP BY ticker, date_t
    HAVING COUNT(*) > 1

    UNION ALL

    SELECT
        'stg_news',
        ticker || ':' || news_id,
        CAST(published_at AS VARCHAR),
        COUNT(*)
    FROM {{ ref('stg_news') }}
    GROUP BY ticker, news_id, published_at
    HAVING COUNT(*) > 1

    UNION ALL

    SELECT
        'int_daily_sentiment',
        ticker,
        CAST(date_t AS VARCHAR),
        COUNT(*)
    FROM {{ ref('int_daily_sentiment') }}
    GROUP BY ticker, date_t
    HAVING COUNT(*) > 1

    UNION ALL

    SELECT
        'int_price_features',
        ticker,
        CAST(date_t AS VARCHAR),
        COUNT(*)
    FROM {{ ref('int_price_features') }}
    GROUP BY ticker, date_t
    HAVING COUNT(*) > 1

    UNION ALL

    SELECT
        'fct_signal_panel',
        ticker,
        CAST(date_t AS VARCHAR),
        COUNT(*)
    FROM {{ ref('fct_signal_panel') }}
    GROUP BY ticker, date_t
    HAVING COUNT(*) > 1
)

SELECT *
FROM duplicate_grains
