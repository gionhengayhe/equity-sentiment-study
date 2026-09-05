-- Do not filter news through today's company master. Historical/delisted tickers
-- remain eligible when they have a contemporaneous price observation.
SELECT *
FROM {{ source('raw_news', 'news') }}
