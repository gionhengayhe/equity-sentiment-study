import json
import hashlib
import datetime
import os
import polars as pl

RAW_PATH = "data/raw/news/crawl_news-{date}.json"
PROCESSED_PATH = "data/processed/news/stg_news-{date}.parquet"


def parse_time(ts: str) -> datetime.datetime:
    return datetime.datetime.strptime(ts, "%Y%m%dT%H%M%S")


def make_news_id(title: str, time_published: str) -> str:
    raw = f"{title}_{time_published}"
    return hashlib.md5(raw.encode()).hexdigest()


def transform_news(date_str: str) -> pl.DataFrame:
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

        # topic_ipo_flag: 1 if any topic is "ipo"
        topic_ipo_flag = int(any(t.get("topic") == "ipo" for t in topics))

        try:
            published_at = parse_time(time_published)
        except ValueError:
            continue

        date_t = published_at.date()
        news_id = make_news_id(title, time_published)

        for ts in ticker_sentiments:
            ticker = ts.get("ticker")
            sentiment_score = ts.get("ticker_sentiment_score")
            relevance_score = ts.get("relevance_score")

            # Filter: skip nulls
            if not ticker or sentiment_score is None or relevance_score is None:
                continue

            sentiment_score = float(sentiment_score)
            relevance_score = float(relevance_score)

            # Filter: low relevance
            if relevance_score < 0.5:
                continue

            rows.append({
                "news_id": news_id,
                "ticker": ticker,
                "published_at": published_at,
                "date_t": date_t,
                "sentiment_score": sentiment_score,
                "relevance_score": relevance_score,
                "source": source,
                "topic_ipo_flag": topic_ipo_flag,
            })

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


def transform_news_range(days: int = 60):
    today = datetime.datetime.now()
    for i in range(2, days + 2):
        date_str = (today - datetime.timedelta(days=i)).strftime("%Y%m%d")
        out_path = PROCESSED_PATH.format(date=date_str)

        if os.path.exists(out_path):
            print(f"[{date_str}] Already transformed, skipping.")
            continue

        try:
            transform_news(date_str)
        except FileNotFoundError as e:
            print(f"[{date_str}] Skipping: {e}")
        except Exception as e:
            print(f"[{date_str}] Failed: {e}")


if __name__ == "__main__":
    transform_news_range(days=60)