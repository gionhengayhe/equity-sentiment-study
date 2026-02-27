import requests
import json
import datetime
import os
import time
from dotenv import load_dotenv

load_dotenv()

RAW_PATH = "data/raw/ohlcs/crawl_ohlcs-{date}.json"
PROCESSED_PATH = "data/processed/ohlcs/stg_ohlcs-{date}.parquet"


def crawl_ohlcs(date: datetime.datetime):
    apiKey = os.getenv("POLYGON_API_KEY")
    if not apiKey:
        raise EnvironmentError("POLYGON_API_KEY is not set.")

    date_crawl = date.strftime("%Y-%m-%d")
    date_str = date.strftime("%Y%m%d")

    url = (
        f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{date_crawl}"
        f"?adjusted=true&include_otc=true&apiKey={apiKey}"
    )

    r = requests.get(url)
    r.raise_for_status()
    data = r.json().get("results", [])

    if not data:
        print(f"[{date_str}] No data returned (market closed or holiday), skipping.")
        return

    path = RAW_PATH.format(date=date_str)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=4)

    print(f"[{date_str}] Crawled {len(data)} OHLCs → {path}")


def crawl_ohlcs_range(days: int = 60):
    today = datetime.datetime.now()

    for i in range(2, days + 2):  # Start from today - 2
        date = today - datetime.timedelta(days=i)

        if date.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            print(f"[{date.strftime('%Y%m%d')}] Weekend, skipping.")
            continue

        date_str = date.strftime("%Y%m%d")
        path = RAW_PATH.format(date=date_str)

        if os.path.exists(path):
            print(f"[{date_str}] Already exists, skipping.")
            continue

        try:
            crawl_ohlcs(date)
            time.sleep(1)  # Polygon free tier: 5 requests/min
        except Exception as e:
            print(f"[{date_str}] Failed: {e}")
            continue


if __name__ == "__main__":
    crawl_ohlcs_range(days=60)