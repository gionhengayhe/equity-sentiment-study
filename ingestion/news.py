import requests
import json
import datetime
import os
import time
from dotenv import load_dotenv

load_dotenv()

RAW_PATH = "data/raw/news/crawl_news-{date}.json"
PROCESSED_PATH = "data/processed/news/stg_news-{date}.parquet"
DAILY_REQUEST_LIMIT = 25


def get_time_range(date: datetime.datetime, time_zone: int):
    if time_zone == 1:
        return date.strftime("%Y%m%dT0000"), date.strftime("%Y%m%dT2359")
    elif time_zone == 2:
        return date.strftime("%Y%m%dT0000"), date.strftime("%Y%m%dT1200")
    else:
        return date.strftime("%Y%m%dT1201"), date.strftime("%Y%m%dT2359")


def crawl_news(date: datetime.datetime, apikey: str) -> tuple[int, int]:
    """
    Crawl news for a single day with time-split logic.
    Returns (articles_count, requests_used).
    
    Logic:
    - timezone 1: full day (0000-2359) → if < 1000 articles, no need to split
    - timezone 2+3: split into AM/PM if full day hit 1000 limit
    """
    date_str = date.strftime("%Y%m%d")
    articles = []
    requests_used = 0

    for time_zone in [1, 2, 3]:
        time_from, time_to = get_time_range(date, time_zone)
        print(f"[{date_str}] Fetching {time_from} → {time_to}")

        time.sleep(1)
        response = requests.get(
            "https://www.alphavantage.co/query",
            params={
                "function": "NEWS_SENTIMENT",
                "time_from": time_from,
                "time_to": time_to,
                "limit": "1000",
                "apikey": apikey,
            }
        ).json()
        requests_used += 1

        if "feed" not in response:
            info = response.get("Information", response.get("Note", str(response)))
            raise KeyError(info)

        data = response["feed"]
        count = len(data)
        print(f"[{date_str}] timezone={time_zone} → {count} articles")

        if time_zone == 1:
            if count < 1000:
                # Under limit — no split needed, save and done
                articles = data
                break
            else:
                # Hit 1000 limit — need to split into AM/PM
                print(f"[{date_str}] Hit 1000 limit, splitting into AM/PM...")
                continue

        # timezone 2 or 3 — accumulate
        articles += data

    # Deduplicate by url in case of overlap
    seen = set()
    deduped = []
    for a in articles:
        url = a.get("url", "")
        if url not in seen:
            seen.add(url)
            deduped.append(a)

    path = RAW_PATH.format(date=date_str)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(deduped, f, indent=4)

    print(f"[{date_str}] Saved {len(deduped)} articles (requests used: {requests_used}) → {path}")
    return len(deduped), requests_used


def crawl_news_range(days: int = 60):
    apikey = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not apikey:
        raise EnvironmentError("ALPHA_VANTAGE_API_KEY is not set.")

    today = datetime.datetime.now()
    requests_used_today = 0

    for i in range(2, days + 2):
        if requests_used_today >= DAILY_REQUEST_LIMIT:
            print(f"\n⚠️  Reached {DAILY_REQUEST_LIMIT} requests limit. Run again tomorrow.")
            print(f"   Remaining days to crawl: {days + 2 - i}")
            break

        date = today - datetime.timedelta(days=i)
        date_str = date.strftime("%Y%m%d")
        path = RAW_PATH.format(date=date_str)

        if os.path.exists(path):
            print(f"[{date_str}] Already exists, skipping.")
            continue

        try:
            _, used = crawl_news(date, apikey)
            requests_used_today += used
        except KeyError as e:
            print(f"[{date_str}] Rate limit hit: {e}")
            print(f"⚠️  Stopping. Requests used today: {requests_used_today}. Run again tomorrow.")
            break
        except Exception as e:
            print(f"[{date_str}] Failed: {e}")
            continue

    print(f"\nDone. Requests used this run: {requests_used_today}/{DAILY_REQUEST_LIMIT}")


if __name__ == "__main__":
    crawl_news_range(days=60)