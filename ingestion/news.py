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


def crawl_news(date: datetime.datetime, apikey: str) -> int:
    """Crawl news for a single day. Returns number of articles fetched."""
    date_str = date.strftime("%Y%m%d")
    time_from = date.strftime("%Y%m%dT0000")
    time_to = date.strftime("%Y%m%dT2359")

    url = (
        f"https://www.alphavantage.co/query"
        f"?function=NEWS_SENTIMENT"
        f"&time_from={time_from}&time_to={time_to}"
        f"&limit=1000&apikey={apikey}"
    )

    time.sleep(1)  # Respect per-second rate limit
    response = requests.get(url).json()

    if "feed" not in response:
        info = response.get("Information", response.get("Note", str(response)))
        raise KeyError(info)

    articles = response["feed"]

    path = RAW_PATH.format(date=date_str)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        json.dump(articles, f, indent=4)

    print(f"[{date_str}] Crawled {len(articles)} articles → {path}")
    return len(articles)


def crawl_news_range(days: int = 60):
    apikey = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not apikey:
        raise EnvironmentError("ALPHA_VANTAGE_API_KEY is not set.")

    today = datetime.datetime.now()
    requests_used = 0

    for i in range(2, days+2):
        if requests_used >= DAILY_REQUEST_LIMIT:
            print(f"\n⚠️  Reached {DAILY_REQUEST_LIMIT} requests limit. Run the script again tomorrow to continue.")
            print(f"   Remaining days to crawl: {days - i}")
            break

        date = today - datetime.timedelta(days=i)
        date_str = date.strftime("%Y%m%d")
        path = RAW_PATH.format(date=date_str)

        if os.path.exists(path):
            print(f"[{date_str}] Already exists, skipping.")
            continue

        try:
            crawl_news(date, apikey)
            requests_used += 1
        except KeyError as e:
            print(f"[{date_str}] Rate limit hit: {e}")
            print(f"⚠️  Stopping. Requests used today: {requests_used}. Run again tomorrow.")
            break
        except Exception as e:
            print(f"[{date_str}] Failed: {e}")
            continue

    print(f"\nDone. Requests used this run: {requests_used}/{DAILY_REQUEST_LIMIT}")


if __name__ == "__main__":
    crawl_news_range(days=60)