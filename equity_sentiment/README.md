# Equity Sentiment dbt Project

Run from this directory with the repository-owned portable profile:

```bash
dbt build --profiles-dir .
```

The default source location is `../data`, the development database is `dev.duckdb`, and the production database is `prod.duckdb`. Override them when needed with:

- `EQUITY_SENTIMENT_DATA_DIR`
- `EQUITY_SENTIMENT_DB_PATH`
- `EQUITY_SENTIMENT_PROD_DB_PATH`

For the full transforms-to-notebook workflow, run this from the repository root:

```bash
python scripts/run_pipeline.py
```
