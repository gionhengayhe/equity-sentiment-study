-- Preserve the full historical grouped-market price tape. The current company
-- master is descriptive enrichment only and must not define past eligibility.
SELECT *
FROM {{ source('raw_ohlcs', 'ohlcs') }}
