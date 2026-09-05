SELECT
    daily.*,
    factors.mkt_rf,
    factors.smb,
    factors.hml,
    factors.mom,
    factors.rf
FROM {{ ref('fct_signal_daily') }} daily
INNER JOIN {{ ref('stg_fama_french_factors') }} factors
    ON daily.return_date_t = factors.date_t
