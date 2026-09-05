import argparse
import requests
import json
import datetime
import os
import time
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = str(PROJECT_ROOT / "data" / "raw" / "ohlcs" / "crawl_ohlcs-{date}.json")
load_dotenv(PROJECT_ROOT / ".env")


def crawl_ohlcs(date: datetime.datetime):
    api_key = os.getenv("POLYGON_API_KEY")
    if not api_key:
        raise EnvironmentError("POLYGON_API_KEY is not set.")

    date_crawl = date.strftime("%Y-%m-%d")
    date_str = date.strftime("%Y%m%d")

    url = (
        f"https://api.polygon.io/v2/aggs/grouped/locale/us/market/stocks/{date_crawl}"
        f"?adjusted=true&include_otc=true&apiKey={api_key}"
    )

    response = requests.get(url, timeout=60)
    response.raise_for_status()
    data = response.json().get("results", [])

    if not data:
        print(f"[{date_str}] No data returned (market closed or holiday), skipping.")
        return

    path = RAW_PATH.format(date=date_str)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)

    print(f"[{date_str}] Crawled {len(data)} OHLCs -> {path}")


def crawl_ohlcs_range(
    days: int = 60,
    sleep_seconds: float = 5.0,
    overwrite: bool = False,
) -> None:
    today = datetime.datetime.now()
    failed_dates: list[str] = []

    for i in range(2, days + 2):  # Start from today - 2
        date = today - datetime.timedelta(days=i)

        if date.weekday() >= 5:  # 5 = Saturday, 6 = Sunday
            print(f"[{date.strftime('%Y%m%d')}] Weekend, skipping.")
            continue

        date_str = date.strftime("%Y%m%d")
        path = RAW_PATH.format(date=date_str)

        if os.path.exists(path) and not overwrite:
            print(f"[{date_str}] Already exists, skipping.")
            continue

        try:
            crawl_ohlcs(date)
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
        except Exception as e:
            print(f"[{date_str}] Failed: {e}")
            failed_dates.append(date_str)

    if failed_dates:
        raise RuntimeError(
            "OHLC ingestion failed for: " + ", ".join(failed_dates)
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download grouped daily US stock OHLC data.")
    parser.add_argument("--days", type=int, default=200)
    parser.add_argument("--sleep-seconds", type=float, default=5.0)
    parser.add_argument("--overwrite", action="store_true")
    arguments = parser.parse_args()
    crawl_ohlcs_range(
        days=arguments.days,
        sleep_seconds=arguments.sleep_seconds,
        overwrite=arguments.overwrite,
    )
