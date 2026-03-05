import json
import glob
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
        .with_columns(
            pl.from_epoch(pl.col("timestamp_ms"), time_unit="ms")
              .dt.convert_time_zone("America/New_York")
              .dt.date()
              .alias("date_t")
        )
        .drop("timestamp_ms")
        .filter(
            (pl.col("close") > 0) &
            (pl.col("volume") > 0) &
            (pl.col("open") > 0) &
            (pl.col("high") > 0) &
            (pl.col("low") > 0)
        )
        .unique(subset=["ticker", "date_t"])
        .sort(["ticker", "date_t"])
    )

    out_path = PROCESSED_PATH.format(date=date_str)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    df.write_parquet(out_path)

    print(f"[{date_str}] Transformed {len(df)} rows → {out_path}")
    return df


def transform_all_ohlcs():
    raw_files = sorted(glob.glob("data/raw/ohlcs/crawl_ohlcs-*.json"))

    if not raw_files:
        print("No raw files found.")
        return

    print(f"Found {len(raw_files)} raw files.")
    skipped = transformed = failed = 0

    for raw_path in raw_files:
        # Extract date from filename: crawl_ohlcs-20260101.json → 20260101
        date_str = os.path.basename(raw_path).replace("crawl_ohlcs-", "").replace(".json", "")
        out_path = PROCESSED_PATH.format(date=date_str)

        if os.path.exists(out_path):
            print(f"[{date_str}] Already exists, skipping.")
            skipped += 1
            continue

        try:
            transform_ohlcs(date_str)
            transformed += 1
        except Exception as e:
            print(f"[{date_str}] Failed: {e}")
            failed += 1

    print(f"\nDone. Transformed: {transformed} | Skipped: {skipped} | Failed: {failed}")


if __name__ == "__main__":
    transform_all_ohlcs()