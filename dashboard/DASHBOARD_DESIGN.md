# Power BI dashboard design

The dashboard is generated from code by `scripts/rebuild_powerbi_dashboard.py`. The script updates the semantic model, report layout, visual formatting, theme, and preview images inside the repository-owned PBIT.

## Audience and decision

Primary audience: a research reviewer deciding whether the financial-news sentiment signal is statistically credible, stable out of sample, and ready for implementation work.

Primary question: does the observed next-session Q5-minus-Q1 return constitute robust tradable alpha?

## Page map

| Page | Reader question | Hero metrics | Visual evidence |
|---|---|---|---|
| 01 Executive Overview | Is the signal credible? | Full-sample mean, compounded return, HAC p-value, factor-adjusted p-value, holdout mean | Cumulative return path and quintile return comparison |
| 02 Robustness & Holdout | Does the finding survive stronger tests? | Factor alpha, training mean, holdout mean, holdout-minus-training difference and bootstrap p-value | Rolling mean, EW versus liquidity-weighted performance, sector, liquidity and news-intensity breakdowns |
| 03 Data Quality & Method | What constrains interpretation? | Signal coverage, panel rows, tickers and articles | Coverage trend, eligible signal universe, date-level diagnostics and canonical definitions |

## Visual system

- Canvas: 1280 × 720, near-white background, white visual cards.
- Palette: navy text, blue primary evidence, teal comparator, amber statistical caution, muted red failed validation.
- No gradients, decorative gauges, funnels, or donut charts.
- KPI cards are full-sample or frozen-split research statistics; date slicers control time-series and diagnostic visuals.
- Trend charts use dates; category comparisons use bars; statistical caveats sit next to the evidence they qualify.

## Refresh

Configure the local ODBC DSN `DuckDB` to point at `equity_sentiment/dev.duckdb`, open `dashboard/equity-sentiment.pbit`, and refresh. The PBIT contains no imported data, so the refresh happens in Power BI Desktop.
