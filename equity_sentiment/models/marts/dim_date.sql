WITH date_spine AS (
    SELECT UNNEST(
        generate_series(
            DATE '2026-01-01',
            DATE '2026-12-31',
            INTERVAL '1 day'
        )
    )::DATE AS full_date
),

-- Get actual trading dates from fact table
actual_trading_days AS (
    SELECT DISTINCT date_t
    FROM {{ ref('fct_signal_panel') }}
),

calendar AS (
    SELECT
        d.full_date,
        CAST(STRFTIME(d.full_date, '%Y%m%d') AS INTEGER)       AS date_key,
        YEAR(d.full_date)                                       AS year,
        QUARTER(d.full_date)                                    AS quarter,
        MONTH(d.full_date)                                      AS month,
        STRFTIME(d.full_date, '%B')                             AS month_name,
        WEEKOFYEAR(d.full_date)                                 AS week_of_year,
        DAYOFWEEK(d.full_date)                                  AS day_of_week,
        STRFTIME(d.full_date, '%A')                             AS day_name,
        DAYOFYEAR(d.full_date)                                  AS day_of_year,

        -- trading_day_flag: TRUE only if date actually exists in fact table
        CASE WHEN t.date_t IS NOT NULL
             THEN 1 ELSE 0 END                                  AS trading_day_flag,

        CASE WHEN d.full_date = LAST_DAY(d.full_date)
             THEN 1 ELSE 0 END                                  AS is_month_end,

        CASE WHEN d.full_date = CAST(DATE_TRUNC('month', d.full_date) AS DATE)
             THEN 1 ELSE 0 END                                  AS is_month_start,

        CASE WHEN MONTH(d.full_date) IN (3, 6, 9, 12)
              AND d.full_date = LAST_DAY(d.full_date)
             THEN 1 ELSE 0 END                                  AS is_quarter_end,

        CASE WHEN MONTH(d.full_date) = 12
              AND DAY(d.full_date) = 31
             THEN 1 ELSE 0 END                                  AS is_year_end

    FROM date_spine d
    LEFT JOIN actual_trading_days t
        ON d.full_date = t.date_t
)

SELECT
    date_key,
    full_date,
    year,
    quarter,
    month,
    month_name,
    week_of_year,
    day_of_week,
    day_name,
    day_of_year,
    is_month_start,
    is_month_end,
    is_quarter_end,
    is_year_end,
    trading_day_flag,

    SUM(trading_day_flag) OVER (
        PARTITION BY year, month
        ORDER BY full_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    )                                                           AS trading_day_of_month

FROM calendar
ORDER BY full_date