import os
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_pipeline import DBT_PROJECT_DIR, PROJECT_ROOT, build_environment


class PipelineConfigurationTests(unittest.TestCase):
    def test_default_paths_are_absolute_and_repository_relative(self):
        empty_overrides = {
            "EQUITY_SENTIMENT_DATA_DIR": "",
            "EQUITY_SENTIMENT_DB_PATH": "",
            "EQUITY_SENTIMENT_PROD_DB_PATH": "",
        }
        with patch.dict(os.environ, empty_overrides, clear=False):
            environment = build_environment("dev")

        self.assertEqual(
            Path(environment["EQUITY_SENTIMENT_DATA_DIR"]),
            (PROJECT_ROOT / "data").resolve(),
        )
        self.assertEqual(
            Path(environment["EQUITY_SENTIMENT_DB_PATH"]),
            (DBT_PROJECT_DIR / "dev.duckdb").resolve(),
        )

    def test_explicit_paths_are_preserved(self):
        overrides = {
            "EQUITY_SENTIMENT_DATA_DIR": "X:/portable/data",
            "EQUITY_SENTIMENT_DB_PATH": "X:/portable/research.duckdb",
        }
        with patch.dict(os.environ, overrides, clear=False):
            environment = build_environment("dev")

        self.assertEqual(environment["EQUITY_SENTIMENT_DATA_DIR"], overrides["EQUITY_SENTIMENT_DATA_DIR"])
        self.assertEqual(environment["EQUITY_SENTIMENT_DB_PATH"], overrides["EQUITY_SENTIMENT_DB_PATH"])


if __name__ == "__main__":
    unittest.main()
