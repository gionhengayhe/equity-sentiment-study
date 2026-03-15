import json
import os
import polars as pl

COMPANY_FIELDS = ["ticker", "name", "exchange", "industry", "sector", "currency", "isDelisted", "category", "sic"]
RAW_PATH = "data/raw/companies/crawl_companies.json"
PROCESSED_PATH = "data/processed/companies/stg_companies.parquet"


def clean_data(df: pl.DataFrame, required_cols: list[str] | None = None) -> pl.DataFrame:
    """Drop rows with nulls in required columns (or all columns if unspecified), then deduplicate."""
    if required_cols:
        df = df.filter(~pl.any_horizontal([pl.col(c).is_null() for c in required_cols]))
    else:
        df = df.drop_nulls()
    return df.unique()


def transform_companies() -> pl.DataFrame:
    with open(RAW_PATH, "r") as f:
        companies = json.load(f)

    records = [{field: company.get(field) for field in COMPANY_FIELDS} for company in companies]
    df = clean_data(pl.DataFrame(records), required_cols=["ticker", "name", "exchange"])

    df_filtered = df.filter(
        (~pl.col("isDelisted")) &
        (pl.col("category") == "Domestic Common Stock") &
        (pl.col("currency") == "USD") &
        (pl.col("sector") != "")
    )

    os.makedirs(os.path.dirname(PROCESSED_PATH), exist_ok=True)
    df_filtered.write_parquet(PROCESSED_PATH)

    print(f"Filtered companies count: {len(df_filtered)} → saved to {PROCESSED_PATH}")
    return df_filtered


if __name__ == "__main__":
    transform_companies()