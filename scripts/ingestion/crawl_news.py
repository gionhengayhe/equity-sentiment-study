import argparse
import datetime as dt
import hashlib
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

API_URL = "https://www.alphavantage.co/query"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = str(PROJECT_ROOT / "data" / "raw" / "news" / "crawl_news-{date}.json")
load_dotenv(PROJECT_ROOT / ".env")
MAX_RESULTS_PER_PAGE = 1000
MIN_SPLIT = dt.timedelta(minutes=1)
DEFAULT_DAILY_REQUEST_LIMIT = 25


class RequestBudgetExceeded(RuntimeError):
    """Raised before an API call that would exceed the configured request budget."""


class SaturatedIntervalError(RuntimeError):
    """Raised when a one-minute interval still reaches the API result cap."""


@dataclass
class RequestBudget:
    limit: int
    used: int = 0

    def consume(self) -> None:
        if self.used >= self.limit:
            raise RequestBudgetExceeded(
                f"Request budget exhausted ({self.used}/{self.limit}); no partial day was saved."
            )
        self.used += 1


def _format_api_time(value: dt.datetime) -> str:
    """Alpha Vantage NEWS_SENTIMENT timestamps are minute-resolution UTC values."""
    return value.strftime("%Y%m%dT%H%M")


def _article_key(article: dict[str, Any]) -> str:
    url = str(article.get("url", "")).strip()
    if url:
        return f"url:{url}"

    stable_payload = {
        "title": article.get("title"),
        "time_published": article.get("time_published"),
        "source": article.get("source"),
    }
    digest = hashlib.sha256(
        json.dumps(stable_payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return f"fallback:{digest}"


def _deduplicate(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for article in articles:
        key = _article_key(article)
        if key not in seen:
            seen.add(key)
            unique.append(article)
    return unique


def _request_json(
    session: Any,
    url: str,
    params: dict[str, Any] | None,
    budget: RequestBudget,
    sleep_seconds: float,
) -> dict[str, Any]:
    budget.consume()
    if sleep_seconds > 0:
        time.sleep(sleep_seconds)

    response = session.get(url, params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()

    if "feed" not in payload:
        message = payload.get("Information", payload.get("Note", payload.get("Error Message")))
        raise RuntimeError(f"News API response did not contain a feed: {message or payload}")
    return payload


def _next_page_request(
    payload: dict[str, Any],
    base_params: dict[str, Any],
) -> tuple[str, dict[str, Any] | None] | None:
    pagination = payload.get("pagination") or {}
    next_url = payload.get("next_url") or payload.get("next") or pagination.get("next_url")
    if next_url:
        return str(next_url), None

    next_token = (
        payload.get("next_token")
        or payload.get("next_page_token")
        or pagination.get("next_token")
    )
    if next_token:
        next_params = dict(base_params)
        next_params["page_token"] = next_token
        return API_URL, next_params
    return None


def _fetch_pages(
    start: dt.datetime,
    end: dt.datetime,
    apikey: str,
    budget: RequestBudget,
    session: Any,
    sleep_seconds: float,
) -> tuple[list[dict[str, Any]], int]:
    base_params: dict[str, Any] = {
        "function": "NEWS_SENTIMENT",
        "time_from": _format_api_time(start),
        "time_to": _format_api_time(end),
        "sort": "EARLIEST",
        "limit": str(MAX_RESULTS_PER_PAGE),
        "apikey": apikey,
    }

    url = API_URL
    params: dict[str, Any] | None = base_params
    articles: list[dict[str, Any]] = []
    terminal_page_size = 0
    page_markers: set[str] = set()

    while True:
        payload = _request_json(session, url, params, budget, sleep_seconds)
        page = payload["feed"]
        articles.extend(page)
        terminal_page_size = len(page)

        next_request = _next_page_request(payload, base_params)
        if next_request is None:
            break

        next_url, next_params = next_request
        marker = next_url if next_params is None else json.dumps(next_params, sort_keys=True)
        if marker in page_markers:
            raise RuntimeError("News API pagination loop detected.")
        page_markers.add(marker)
        url, params = next_url, next_params

    return articles, terminal_page_size


def fetch_news_interval(
    start: dt.datetime,
    end: dt.datetime,
    apikey: str,
    budget: RequestBudget,
    session: Any = requests,
    sleep_seconds: float = 1.0,
    depth: int = 0,
) -> list[dict[str, Any]]:
    """Fetch a complete UTC interval using pagination, then recursive time splitting."""
    indent = "  " * depth
    print(f"{indent}Fetching {_format_api_time(start)} -> {_format_api_time(end)}")
    articles, terminal_page_size = _fetch_pages(
        start, end, apikey, budget, session, sleep_seconds
    )

    if terminal_page_size < MAX_RESULTS_PER_PAGE:
        return _deduplicate(articles)

    if end - start < MIN_SPLIT:
        raise SaturatedIntervalError(
            f"Interval {_format_api_time(start)} -> {_format_api_time(end)} still returned "
            f"{terminal_page_size} rows. Completeness cannot be guaranteed."
        )

    total_minutes = int((end - start).total_seconds() // 60)
    midpoint = start + dt.timedelta(minutes=total_minutes // 2)
    right_start = midpoint + MIN_SPLIT
    print(f"{indent}Result cap reached; splitting interval recursively.")

    left = fetch_news_interval(
        start, midpoint, apikey, budget, session, sleep_seconds, depth + 1
    )
    right = fetch_news_interval(
        right_start, end, apikey, budget, session, sleep_seconds, depth + 1
    )
    return _deduplicate(left + right)


def crawl_news(
    date: dt.datetime,
    apikey: str,
    budget: RequestBudget | None = None,
    session: Any = requests,
    sleep_seconds: float = 1.0,
) -> tuple[int, int]:
    """Fetch one complete UTC calendar day and save only after all splits succeed."""
    if budget is None:
        budget = RequestBudget(DEFAULT_DAILY_REQUEST_LIMIT)
    requests_before = budget.used

    start = date.replace(hour=0, minute=0, second=0, microsecond=0)
    end = date.replace(hour=23, minute=59, second=0, microsecond=0)
    articles = fetch_news_interval(
        start, end, apikey, budget, session=session, sleep_seconds=sleep_seconds
    )

    date_str = date.strftime("%Y%m%d")
    path = RAW_PATH.format(date=date_str)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(articles, handle, indent=2, ensure_ascii=False)

    requests_used = budget.used - requests_before
    print(f"[{date_str}] Saved {len(articles)} articles ({requests_used} requests) -> {path}")
    return len(articles), requests_used


def crawl_news_range(
    days: int = 200,
    request_limit: int = DEFAULT_DAILY_REQUEST_LIMIT,
    sleep_seconds: float = 1.0,
    overwrite: bool = False,
) -> None:
    apikey = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not apikey:
        raise EnvironmentError("ALPHA_VANTAGE_API_KEY is not set.")

    today_utc = dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)
    budget = RequestBudget(request_limit)
    failed_dates: list[str] = []

    for offset in range(2, days + 2):
        date = today_utc - dt.timedelta(days=offset)
        date_str = date.strftime("%Y%m%d")
        path = RAW_PATH.format(date=date_str)

        if os.path.exists(path) and not overwrite:
            print(f"[{date_str}] Already exists, skipping.")
            continue

        try:
            crawl_news(date, apikey, budget=budget, sleep_seconds=sleep_seconds)
        except RequestBudgetExceeded as exc:
            raise RequestBudgetExceeded(
                f"{exc} Requested range is incomplete; rerun with a larger budget."
            ) from exc
        except SaturatedIntervalError:
            raise
        except Exception as exc:
            print(f"[{date_str}] Failed: {exc}")
            failed_dates.append(date_str)

    print(f"Done. Requests used this run: {budget.used}/{budget.limit}")
    if failed_dates:
        raise RuntimeError(
            "News ingestion failed for: " + ", ".join(failed_dates)
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Crawl complete Alpha Vantage news days with pagination and recursive splitting."
    )
    parser.add_argument("--days", type=int, default=200)
    parser.add_argument("--request-limit", type=int, default=DEFAULT_DAILY_REQUEST_LIMIT)
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    crawl_news_range(
        days=args.days,
        request_limit=args.request_limit,
        sleep_seconds=args.sleep_seconds,
        overwrite=args.overwrite,
    )
