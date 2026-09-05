import argparse
import csv
import io
import json
import os
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import polars as pl
import requests

FF3_DAILY_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_Factors_daily_CSV.zip"
)
MOM_DAILY_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Momentum_Factor_daily_CSV.zip"
)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = str(PROJECT_ROOT / "data" / "processed" / "factors" / "fama_french_daily.parquet")
METADATA_PATH = str(PROJECT_ROOT / "data" / "processed" / "factors" / "fama_french_daily_metadata.json")


def _download_zip(url: str, session=requests) -> bytes:
    response = session.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def _parse_factor_zip(content: bytes, required_columns: set[str]) -> list[dict[str, str]]:
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError(f"Expected one CSV in factor archive, found {csv_names}")
        text = archive.read(csv_names[0]).decode("utf-8-sig", errors="replace")

    lines = text.splitlines()
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if required_columns.issubset({part.strip() for part in line.split(",")})
        ),
        None,
    )
    if header_index is None:
        raise ValueError(f"Factor header not found; required columns: {required_columns}")

    rows: list[dict[str, str]] = []
    reader = csv.DictReader(lines[header_index:])
    date_column = reader.fieldnames[0]
    for row in reader:
        raw_date = (row.get(date_column) or "").strip()
        if len(raw_date) != 8 or not raw_date.isdigit():
            if rows:
                break
            continue
        rows.append({(key or "date").strip(): (value or "").strip() for key, value in row.items()})
    return rows


def crawl_fama_french_factors(session=requests) -> int:
    ff3_rows = _parse_factor_zip(
        _download_zip(FF3_DAILY_URL, session), {"Mkt-RF", "SMB", "HML", "RF"}
    )
    momentum_rows = _parse_factor_zip(
        _download_zip(MOM_DAILY_URL, session), {"Mom"}
    )

    momentum_by_date = {row["date"]: float(row["Mom"]) / 100 for row in momentum_rows}
    records = []
    for row in ff3_rows:
        date_key = row["date"]
        if date_key not in momentum_by_date:
            continue
        records.append(
            {
                "date_t": datetime.strptime(date_key, "%Y%m%d").date(),
                "mkt_rf": float(row["Mkt-RF"]) / 100,
                "smb": float(row["SMB"]) / 100,
                "hml": float(row["HML"]) / 100,
                "mom": momentum_by_date[date_key],
                "rf": float(row["RF"]) / 100,
            }
        )

    if not records:
        raise RuntimeError("No overlapping Fama-French and momentum factor rows were parsed.")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    pl.DataFrame(records).sort("date_t").write_parquet(OUTPUT_PATH)
    metadata = {
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(),
        "sources": [FF3_DAILY_URL, MOM_DAILY_URL],
        "units": "decimal daily returns",
        "row_count": len(records),
        "min_date": str(records[0]["date_t"]),
        "max_date": str(records[-1]["date_t"]),
    }
    with open(METADATA_PATH, "w", encoding="utf-8") as handle:
        json.dump(metadata, handle, indent=2)

    print(
        f"Saved {len(records)} daily factor rows "
        f"({metadata['min_date']} -> {metadata['max_date']}) to {OUTPUT_PATH}"
    )
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download daily US Fama-French factors.")
    parser.parse_args()
    crawl_fama_french_factors()
