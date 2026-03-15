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
5. Analyze signal stability and cross-sectional behavior.

To reduce noise, the dataset only includes stock-days where:

- `has_sentiment_flag = 1`
- `news_count > 1`

This ensures sentiment signals are based on **multiple independent news articles**.

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
- `stg_ohlcs`: price bars and volume history
- `int_daily_sentiment`: per-symbol daily sentiment metrics
- `int_price_features`: returns and price-based features
- `fct_signal_panel`: cross-sectional sentiment ranks and quantiles
- `fct_signal_daily`: portfolio returns and daily strategy performance
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

3. Run dbt:

```bash
cd equity_sentiment
dbt deps
dbt seed
dbt run
dbt test
```

4. Run notebook analysis:

- `notebooks/news_sentiment_alpha_research.ipynb`

---

## Project structure

- `scripts/`: source data ingestion scripts
- `equity_sentiment/`: dbt models, seeds, snapshots, tests
- `notebooks/`: notebooks and research output
- `data/raw/`: raw news and company JSON
- `data/processed/`: cleaned and derived tables
- `README.md`: this file

---

## Key findings

- Positive news sentiment is associated with higher next-day returns on average.
- Signal strength degrades as the market absorbs information.
- Strongest signals when a stock has `> 1` independent news mention and low liquidity.

---

## Improvements and next steps

- Add factor-adjusted controls (momentum, size, value, liquidity).
- Evaluate transaction costs and slippage.
- Test sector-neutral and industry-neutral portfolio construction.
- Extend to intraday news timestamps.

---

## Validation

In `equity_sentiment` run:

```bash
dbt test
```

confirm model quality and column expectations.

---
