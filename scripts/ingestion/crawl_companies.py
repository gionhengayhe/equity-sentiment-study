import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

RAW_PATH = "data/raw/companies/crawl_companies.json"


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


if __name__ == "__main__":
    crawl_companies()