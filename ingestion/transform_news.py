from bisect import bisect_right
import glob
import json
import hashlib
from datetime import datetime, date, time, timedelta
import os
import polars as pl
import pytz

RAW_PATH = "data/raw/news/crawl_news-{date}.json"
PROCESSED_PATH = "data/processed/news/stg_news-{date}.parquet"

MARKET_CLOSE = time(16, 0)
ET = pytz.timezone("America/New_York")
UTC = pytz.utc


def get_trading_days() -> tuple[list, set]:
    files = glob.glob("data/processed/ohlcs/stg_ohlcs-*.parquet")
    if not files:
        raise FileNotFoundError("No processed ohlcs parquet files found.")

    trading_days = (
        pl.scan_parquet(files)
        .select("date_t")
        .unique()
        .sort("date_t")
        .collect()
        .to_series()
        .to_list()
    )
    trading_days_set = set(trading_days)
    print(f"Found {len(trading_days)} trading days: {trading_days[0]} → {trading_days[-1]}")
    return trading_days, trading_days_set


def get_next_trading_day(current_date, trading_days: list):
    idx = bisect_right(trading_days, current_date)
    if idx < len(trading_days):
        return trading_days[idx]
    return None


def make_news_id(title: str, time_published: str) -> str:
    raw = f"{title}_{time_published}"
    return hashlib.md5(raw.encode()).hexdigest()


def transform_news(date_str: str, trading_days: list, trading_days_set: set) -> pl.DataFrame:
    path = RAW_PATH.format(date=date_str)
    if not os.path.exists(path):
        raise FileNotFoundError(f"No raw file found at {path}")

    with open(path, "r") as f:
        articles = json.load(f)

    rows = []
    for article in articles:
        title = article.get("title", "")
        time_published = article.get("time_published", "")
        source = article.get("source", "")
        topics = article.get("topics", [])
        ticker_sentiments = article.get("ticker_sentiment", [])

        topic_ipo_flag = int(any(t.get("topic") == "ipo" for t in topics))

        try:
            published_at_utc = datetime.strptime(time_published, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
            published_at_et = published_at_utc.astimezone(ET)
        except ValueError:
            continue

        calendar_date = published_at_et.date()

        if published_at_et.time() > MARKET_CLOSE:
            date_t = get_next_trading_day(calendar_date, trading_days)
        else:
            if calendar_date in trading_days_set:
                date_t = calendar_date
            else:
                date_t = get_next_trading_day(calendar_date, trading_days)

        if date_t is None:
            continue

        news_id = make_news_id(title, time_published)

        for ts in ticker_sentiments:
            ticker = ts.get("ticker")
            sentiment_score = ts.get("ticker_sentiment_score")
            relevance_score = ts.get("relevance_score")

            if not ticker or sentiment_score is None or relevance_score is None:
                continue

            sentiment_score = float(sentiment_score)
            relevance_score = float(relevance_score)

            if relevance_score < 0.5:
                continue

            rows.append({
                "news_id": news_id,
                "ticker": ticker,
                "published_at": published_at_et.replace(tzinfo=None),
                "date_t": date_t,
                "sentiment_score": sentiment_score,
                "relevance_score": relevance_score,
                "source": source,
                "topic_ipo_flag": topic_ipo_flag,
            })

    if not rows:
        print(f"[{date_str}] No valid rows after filtering.")
        return pl.DataFrame()

    df = (
        pl.DataFrame(rows)
        .with_columns([
            pl.col("published_at").cast(pl.Datetime),
            pl.col("date_t").cast(pl.Date),
        ])
        .unique(subset=["ticker", "published_at", "news_id"])
        .sort("published_at", descending=True)
    )

    out_path = PROCESSED_PATH.format(date=date_str)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.write_parquet(out_path)

    print(f"[{date_str}] Transformed {len(df)} ticker-news rows → {out_path}")
    return df


def transform_all_news():
    trading_days, trading_days_set = get_trading_days()

    raw_files = sorted(glob.glob("data/raw/news/crawl_news-*.json"))
    if not raw_files:
        print("No raw news files found.")
        return

    print(f"Found {len(raw_files)} raw files.")
    skipped = transformed = failed = 0

    for raw_path in raw_files:
        # Extract date from filename: crawl_news-20260101.json → 20260101
        date_str = os.path.basename(raw_path).replace("crawl_news-", "").replace(".json", "")
        out_path = PROCESSED_PATH.format(date=date_str)

        if os.path.exists(out_path):
            print(f"[{date_str}] Already exists, skipping.")
            skipped += 1
            continue

        try:
            transform_news(date_str, trading_days, trading_days_set)
            transformed += 1
        except FileNotFoundError as e:
            print(f"[{date_str}] Skipping: {e}")
            failed += 1
        except Exception as e:
            print(f"[{date_str}] Failed: {e}")
            failed += 1

    print(f"\nDone. Transformed: {transformed} | Skipped: {skipped} | Failed: {failed}")


if __name__ == "__main__":
    transform_all_news()