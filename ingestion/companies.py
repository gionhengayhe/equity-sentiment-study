from datetime import datetime
import requests
import json
import os
import polars as pl
from dotenv import load_dotenv

load_dotenv()
COMPANY_FIELDS = ["ticker", "name", "exchange", "industry", "sector", "currency", "isDelisted", "category", "sic"]
RAW_PATH = "data/raw/companies.json"
PROCESSED_PATH = "data/processed/companies.parquet"


def crawl_companies(exchanges: list[str] = ["NASDAQ", "NYSE"]) -> None:
    api_key = os.getenv("SEC_API_KEY")
    if not api_key:
        raise EnvironmentError("SEC_API_KEY environment variable is not set.")

    list_companies = []
    for exchange in exchanges:
        url = f"https://api.sec-api.io/mapping/exchange/{exchange}?token={api_key}"
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        list_companies.extend(data)
        print(f"Fetched {len(data)} companies from {exchange} exchange.")

    os.makedirs(os.path.dirname(RAW_PATH), exist_ok=True)
    with open(RAW_PATH, "w") as f:
        json.dump(list_companies, f, indent=4)

    print(f"Crawled {len(list_companies)} companies → saved to {RAW_PATH}")


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
        (pl.col("currency") == "USD")
    )

    os.makedirs(os.path.dirname(PROCESSED_PATH), exist_ok=True)
    df_filtered.write_parquet(PROCESSED_PATH)

    print(f"Filtered companies count: {len(df_filtered)} → saved to {PROCESSED_PATH}")
    return df_filtered

if __name__ == "__main__":
    crawl_companies()
    transform_companies()