# Financial News Sentiment Alpha Study

An end-to-end quantitative research project investigating whether financial news sentiment predicts short-term equity returns.

## Overview

Using financial news and daily equity prices, the project constructs a cross-sectional sentiment signal and evaluates a simple long–short strategy: long stocks with the most positive sentiment and short those with the most negative sentiment.

The project implements an **end-to-end workflow** including **data ingestion, sentiment aggregation, signal construction, empirical testing**, and **dashboard visualization**.

---

## Problem Statement

The project began with a simple question:

> **Does financial news sentiment influence stock prices?**

This leads to several follow-up questions:

- Do stocks with **positive sentiment** outperform those with **negative sentiment**?
- How quickly does the market react to sentiment signals?
- Can sentiment signals be used to build a **systematic trading signal**?

To explore this idea, the project tests a basic strategy:

**Long stocks with the most positive sentiment and short stocks with the most negative sentiment**, holding the position for the next trading day.

---

## Research Approach

The research follows a typical **quantitative signal research workflow**:

1. Collect financial news and stock price data.
2. Aggregate article-level sentiment to **stock-day signals**.
3. Rank stocks by sentiment and construct **quintile portfolios**.
4. Evaluate the **long–short sentiment spread**.
5. Analyze signal stability, factor-adjusted alpha, and chronological out-of-sample behavior.

To reduce noise, the dataset only includes stock-days where:

- `has_sentiment_flag = 1`
- `news_count > 1`

This requires multiple qualifying ticker-article observations. It does not guarantee independent information because syndicated articles may repeat across sources.

### Canonical research definitions

- **Signal cutoff:** `16:00:00 America/New_York`, exclusive. News published before 16:00 contributes to that trading day's closing signal; news published at or after 16:00 is assigned to the next available trading day.
- **Signal date (`date_t`):** the trading close at which the cross-sectional signal is observed and the portfolio is formed.
- **Return horizon:** `close(date_t) -> close(next market trading session)`. The horizon is defined by the common market calendar, not the next row available for an individual ticker. A ticker without a close on that exact next session has a null forward return and is excluded from that day's portfolio. The explicit model field is `forward_return_close_to_close_1d`.
- **Daily portfolio:** equal-weighted Q5 minus equal-weighted Q1. Each leg has one unit of capital, so the strategy has 200% gross exposure and 0% net exposure before costs.
- **Liquidity-weighted portfolio:** uses dollar volume as the weight and is labeled `lw`; it is not market-cap value weighting. Legacy `vw` fields remain only for dashboard compatibility.
- **Cumulative return:** compounds daily long-short returns as `PRODUCT(1 + long_short_return) - 1`. `cumulative_spread` is the arithmetic sum and is retained only as a research diagnostic.
- **Factor date:** factor returns are joined on `return_date_t`, the next-session date when the portfolio return is realized, rather than the signal date.
- **Inference:** reported mean returns and alphas use Newey–West HAC with five lags; subgroup results also use a five-day circular moving-block bootstrap and Holm-adjusted subgroup p-values.
- **Out of sample:** 2025-12-15 is the frozen chronological holdout start; construction and inference rules are unchanged across the split. This is a retrospective pseudo-out-of-sample check, not a prospective live test.

### Point-in-time universe and ingestion completeness

- The historical price tape determines ticker eligibility on each date. The current company master is only optional descriptive enrichment and cannot filter historical or delisted tickers, removing the prior structural survivorship filter.
- The current input does not contain a point-in-time security-type master, so historical common-stock-only membership cannot yet be guaranteed.
- News ingestion follows explicit continuation URLs/tokens when supplied. If an Alpha Vantage interval reaches the 1,000-result cap, it is split recursively to minute resolution; a still-saturated one-minute interval fails loudly instead of being saved as complete.
- A request-budget exhaustion never writes a partial daily file.

---

## Data Pipeline

`News data` + `Price data` ➜ `Data Warehouse` ➜ `Feature Engineering (dbt)` ➜ `Signal Construction` ➜ `Research analysis (Notebook)` ➜ `Visualization (Power BI)`

### Core technologies

- Python (data processing)
- DuckDB (analytics warehouse)
- dbt (transforms and model orchestration)
- Jupyter Notebook (research and plotting)
- Power BI (visualization)

---

## Data Model

Layered architecture:

- `stg_` tables: raw cleaned data
- `int_` tables: intermediate features
- `fct_` tables: final signal datasets

Main tables:

- `stg_news`: raw news article records + sentiment
- `stg_fama_french_factors`: daily US market, size, value, momentum, and risk-free factors
- `stg_ohlcs`: price bars and volume history
- `int_daily_sentiment`: per-symbol daily sentiment metrics
- `int_price_features`: returns and price-based features
- `fct_signal_panel`: cross-sectional sentiment ranks and quantiles
- `fct_signal_daily`: portfolio returns and daily strategy performance
- `fct_signal_daily_factors`: daily strategy returns matched to factors on the realized return date
- `fct_signal_rolling`: rolling alpha / risk measures

---

## Quick start

1. Clone repo:

```bash
git clone https://github.com/gionhengayhe/equity-sentiment-study.git
cd equity-sentiment-study
```

2. Set up Python env:

```bash
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

3. Run the complete reproducible pipeline from existing raw inputs:

```bash
python scripts/run_pipeline.py
```

This performs all local transforms, refreshes Fama–French factors, runs Python unit tests, executes `dbt build`, executes the research notebook in place, refreshes its HTML report, synchronizes the Power BI template schema, and rebuilds the PDF research report. Every stage fails fast; a downstream stage is not run after an upstream error.

To refresh all remote inputs first, copy `.env.example` to `.env`, configure the three API keys, and run:

```bash
python scripts/run_pipeline.py --ingest --days 200 --news-request-limit 500
```

Useful repeat-run options:

```bash
python scripts/run_pipeline.py --skip-factor-download
python scripts/run_pipeline.py --overwrite-transforms
python scripts/run_pipeline.py --skip-notebook
python scripts/run_pipeline.py --skip-dashboard
```

For a manual dbt-only run, use the repository-owned profile rather than a user-level `~/.dbt/profiles.yml`:

```bash
cd equity_sentiment
dbt build --profiles-dir .
```

### Portable configuration

- All Python paths are derived from each script's location, so scripts do not depend on the current working directory.
- dbt sources use `EQUITY_SENTIMENT_DATA_DIR`, defaulting to `../data` when dbt is run from `equity_sentiment/`.
- DuckDB uses `EQUITY_SENTIMENT_DB_PATH` for `dev` and `EQUITY_SENTIMENT_PROD_DB_PATH` for `prod`.
- `scripts/run_pipeline.py` sets absolute portable values for these variables automatically.
- Credentials and optional overrides are documented in `.env.example`; secrets remain in the ignored `.env` file.

### Automated checks

The dbt build currently runs 61 data tests covering required fields, unique model grains, OHLC validity, news-score ranges, signal timing, sentiment aggregation, point-in-time universe integrity, exact return horizon, portfolio identities and coverage, cumulative compounding, and factor coverage on `return_date_t`.

---

## Project structure

- `scripts/`: source data ingestion scripts
- `scripts/run_pipeline.py`: cross-platform end-to-end pipeline entry point
- `scripts/rebuild_dashboard_artifacts.py`: deterministic PBIT schema and PDF report builder
- `scripts/rebuild_powerbi_dashboard.py`: code-generated, story-led Power BI layout and preview builder
- `equity_sentiment/`: dbt models
- `notebooks/`: notebooks and research output
- `dashboard/`: Power BI template, PDF report, metric definitions, and machine-readable research summary
- `data/raw/`: raw news and company JSON
- `data/processed/`: cleaned and derived tables
- `README.md`: this file

---

## Key findings

These figures are synchronized from `dashboard/research_summary.json` after the end-to-end DuckDB, notebook, PBIT, and PDF rebuild.

- On the rebuilt 132-day sample (signal dates 2025-08-18 through 2026-03-03), the equal-weight Q5-minus-Q1 portfolio averages 0.236% per day. The estimate is borderline significant under Newey–West HAC (`p = 0.0416`) and a five-day moving-block bootstrap (`p = 0.0468`) before costs; compounded full-sample return is 34.13%.
- FF3+momentum-adjusted daily alpha is 0.207%, but its 95% HAC interval includes zero (`p = 0.0990`).
- The frozen pre-holdout sample has 79 days and averages 0.412% per day. The 53-day holdout averages -0.027% (`p = 0.8486`) and compounds to -1.65%. The holdout-minus-training difference is -0.438 percentage points per day and is significant in the block bootstrap (`p = 0.0368`).
- The mid-liquidity subgroup survives Holm correction (`p = 0.0341`), but low-minus-high liquidity is insignificant (`p = 0.7247`). The 2–3 article subgroup does not survive Holm correction (`p = 0.1197`), and the 5+-minus-2–3 direct contrast is also insignificant (`p = 0.0592`). These tests do not establish a monotonic subgroup effect.
- The positive full-sample association does not persist out of sample and is not statistically significant after factor adjustment. It is therefore not reliable evidence of tradable alpha, especially before transaction costs, financing, short-borrow constraints, slippage, and corporate-action adjustments.

---

## Improvements and next steps

- Evaluate transaction costs and slippage.
- Test sector-neutral and industry-neutral portfolio construction.
- Add intraday price horizons to test response timing and signal decay.
- Add point-in-time security classifications, delisting returns, corporate-action validation, and borrow availability.

---
