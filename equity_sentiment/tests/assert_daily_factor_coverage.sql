SELECT daily.date_t
FROM {{ ref('fct_signal_daily') }} daily
LEFT JOIN {{ ref('stg_fama_french_factors') }} factors
    ON daily.return_date_t = factors.date_t
WHERE factors.date_t IS NULL
