SELECT
    CAST(date_t AS DATE) AS date_t,
    CAST(mkt_rf AS DOUBLE) AS mkt_rf,
    CAST(smb AS DOUBLE) AS smb,
    CAST(hml AS DOUBLE) AS hml,
    CAST(mom AS DOUBLE) AS mom,
    CAST(rf AS DOUBLE) AS rf
FROM {{ source('raw_factors', 'fama_french_daily') }}
