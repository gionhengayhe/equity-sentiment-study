SELECT
    ticker,
    date_t,
    news_count,
    has_sentiment_flag,
    company_metadata_available_flag,
    point_in_time_universe_flag,
    liquidity_bucket,
    news_count_bucket
FROM {{ ref('fct_signal_panel') }}
WHERE news_count <= 1
   OR has_sentiment_flag != 1
   OR company_metadata_available_flag NOT IN (0, 1)
   OR point_in_time_universe_flag != 1
   OR liquidity_bucket NOT IN ('Low Liquidity', 'Mid Liquidity', 'High Liquidity')
   OR news_count_bucket NOT IN ('2-3', '4-5', '5+')
