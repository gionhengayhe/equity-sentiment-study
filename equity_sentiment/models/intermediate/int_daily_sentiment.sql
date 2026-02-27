SELECT
    ticker,
    date_t,
    sum(sentiment_score * relevance_score)
        / nullif(sum(relevance_score), 0) 
        as weighted_sentiment,
    COUNT(*)                                                    AS news_count,
    sum(relevance_score)                                        AS total_relevance,
    ln(count(*) + 1)                                            AS log_news_count
FROM {{ ref('stg_news') }}
GROUP BY ticker, date_t