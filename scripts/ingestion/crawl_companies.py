import argparse
import requests
import json
import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = str(PROJECT_ROOT / "data" / "raw" / "companies" / "crawl_companies.json")
load_dotenv(PROJECT_ROOT / ".env")


def crawl_companies(exchanges: tuple[str, ...] = ("NASDAQ", "NYSE")) -> None:
    api_key = os.getenv("SEC_API_KEY")
    if not api_key:
        raise EnvironmentError("SEC_API_KEY environment variable is not set.")

    list_companies = []
    for exchange in exchanges:
        url = f"https://api.sec-api.io/mapping/exchange/{exchange}?token={api_key}"
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        data = response.json()
        list_companies.extend(data)
        print(f"Fetched {len(data)} companies from {exchange} exchange.")

    os.makedirs(os.path.dirname(RAW_PATH), exist_ok=True)
    with open(RAW_PATH, "w", encoding="utf-8") as handle:
        json.dump(list_companies, handle, indent=2, ensure_ascii=False)

    print(f"Crawled {len(list_companies)} companies -> saved to {RAW_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download current company metadata.")
    parser.add_argument("--exchanges", nargs="+", default=["NASDAQ", "NYSE"])
    arguments = parser.parse_args()
    crawl_companies(tuple(arguments.exchanges))
