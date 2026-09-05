import datetime as dt
import unittest

from scripts.ingestion.crawl_news import (
    MAX_RESULTS_PER_PAGE,
    RequestBudget,
    SaturatedIntervalError,
    fetch_news_interval,
)


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, responder):
        self.responder = responder
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        return FakeResponse(self.responder(url, params))


class CrawlNewsTests(unittest.TestCase):
    def test_follows_next_url_pages(self):
        def responder(url, params):
            if url == "page-2":
                return {"feed": [{"url": "b"}]}
            return {"feed": [{"url": "a"}], "next_url": "page-2"}

        session = FakeSession(responder)
        rows = fetch_news_interval(
            dt.datetime(2026, 1, 1),
            dt.datetime(2026, 1, 1, 23, 59),
            "test-key",
            RequestBudget(5),
            session=session,
            sleep_seconds=0,
        )

        self.assertEqual([row["url"] for row in rows], ["a", "b"])
        self.assertEqual(len(session.calls), 2)

    def test_recursively_splits_a_saturated_interval(self):
        saturated = [{"url": f"full-{index}"} for index in range(MAX_RESULTS_PER_PAGE)]

        def responder(url, params):
            if params["time_from"].endswith("T0000") and params["time_to"].endswith("T2359"):
                return {"feed": saturated}
            if params["time_to"].endswith("T1159"):
                return {"feed": [{"url": "left"}]}
            return {"feed": [{"url": "right"}]}

        session = FakeSession(responder)
        rows = fetch_news_interval(
            dt.datetime(2026, 1, 1),
            dt.datetime(2026, 1, 1, 23, 59),
            "test-key",
            RequestBudget(5),
            session=session,
            sleep_seconds=0,
        )

        self.assertEqual([row["url"] for row in rows], ["left", "right"])
        self.assertEqual(session.calls[1][1]["time_to"], "20260101T1159")
        self.assertEqual(session.calls[2][1]["time_from"], "20260101T1200")

    def test_raises_when_one_minute_is_still_saturated(self):
        session = FakeSession(
            lambda url, params: {
                "feed": [{"url": str(index)} for index in range(MAX_RESULTS_PER_PAGE)]
            }
        )

        with self.assertRaises(SaturatedIntervalError):
            fetch_news_interval(
                dt.datetime(2026, 1, 1, 12, 0),
                dt.datetime(2026, 1, 1, 12, 0),
                "test-key",
                RequestBudget(2),
                session=session,
                sleep_seconds=0,
            )


if __name__ == "__main__":
    unittest.main()
