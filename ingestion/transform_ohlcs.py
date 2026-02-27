import json
import datetime
import os
import polars as pl

RAW_PATH = "data/raw/ohlcs/crawl_ohlcs-{date}.json"
PROCESSED_PATH = "data/processed/ohlcs/stg_ohlcs-{date}.parquet"


def transform_ohlcs(date_str: str) -> pl.DataFrame:
    path = RAW_PATH.format(date=date_str)
    if not os.path.exists(path):
        raise FileNotFoundError(f"No raw file found at {path}")

    with open(path, "r") as f:
        raw = json.load(f)

    if not raw:
        print(f"[{date_str}] Empty file, skipping.")
        return pl.DataFrame()

    df = (
        pl.DataFrame(raw)
        .rename({
            "T": "ticker",
            "t": "timestamp_ms",
            "o": "open",
            "h": "high",
            "l": "low",
            "c": "close",
            "v": "volume",
        })
        .select(["ticker", "timestamp_ms", "open", "high", "low", "close", "volume"])

        # Convert ms timestamp → datetime (UTC) → US/Eastern date
        .with_columns(
            pl.from_epoch(pl.col("timestamp_ms"), time_unit="ms")
              .dt.convert_time_zone("America/New_York")
              .dt.date()
              .alias("date_t")
        )
        .drop("timestamp_ms")

        # Filters
        .filter(
            (pl.col("close") > 0) &
            (pl.col("volume") > 0) &
            (pl.col("open") > 0) &
            (pl.col("high") > 0) &
            (pl.col("low") > 0)
        )

        # Deduplicate
        .unique(subset=["ticker", "date_t"])
        .sort(["ticker", "date_t"])
    )

    out_path = PROCESSED_PATH.format(date=date_str)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.write_parquet(out_path)

    print(f"[{date_str}] Transformed {len(df)} rows → {out_path}")
    return df


def transform_ohlcs_range(days: int = 60):
    today = datetime.datetime.now()

    for i in range(2, days + 2):
        date = today - datetime.timedelta(days=i)

        if date.weekday() >= 5:  # Skip weekends, same as crawl
            print(f"[{date.strftime('%Y%m%d')}] Weekend, skipping.")
            continue
        date_str = date.strftime("%Y%m%d")
        out_path = PROCESSED_PATH.format(date=date_str)

        if os.path.exists(out_path):
            print(f"[{date_str}] Already transformed, skipping.")
            continue

        try:
            transform_ohlcs(date_str)
        except FileNotFoundError as e:
            print(f"[{date_str}] Skipping: {e}")
        except Exception as e:
            print(f"[{date_str}] Failed: {e}")


if __name__ == "__main__":
    transform_ohlcs_range(days=60)