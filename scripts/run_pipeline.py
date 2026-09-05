from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = PROJECT_ROOT / "equity_sentiment"
NOTEBOOK_PATH = PROJECT_ROOT / "notebooks" / "news_sentiment_alpha_research.ipynb"


def run_step(
    label: str,
    command: list[str],
    *,
    cwd: Path = PROJECT_ROOT,
    environment: dict[str, str],
) -> None:
    print(f"\n=== {label} ===", flush=True)
    print(" ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=environment, check=True)


def require_local_inputs() -> None:
    required_single_files = [
        PROJECT_ROOT / "data" / "raw" / "companies" / "crawl_companies.json",
    ]
    required_globs = [
        PROJECT_ROOT / "data" / "raw" / "ohlcs" / "crawl_ohlcs-*.json",
        PROJECT_ROOT / "data" / "raw" / "news" / "crawl_news-*.json",
    ]

    missing = [str(path) for path in required_single_files if not path.exists()]
    missing.extend(str(pattern) for pattern in required_globs if not list(pattern.parent.glob(pattern.name)))
    if missing:
        raise FileNotFoundError(
            "Missing raw pipeline inputs:\n- " + "\n- ".join(missing)
            + "\nRun with --ingest after configuring API keys."
        )


def build_environment(target: str) -> dict[str, str]:
    environment = os.environ.copy()
    environment["EQUITY_SENTIMENT_DATA_DIR"] = environment.get(
        "EQUITY_SENTIMENT_DATA_DIR"
    ) or (PROJECT_ROOT / "data").resolve().as_posix()

    selected_database_variable = (
        "EQUITY_SENTIMENT_DB_PATH"
        if target == "dev"
        else "EQUITY_SENTIMENT_PROD_DB_PATH"
    )
    selected_database_path = environment.get(selected_database_variable) or (
        DBT_PROJECT_DIR / f"{target}.duckdb"
    ).resolve().as_posix()
    environment[selected_database_variable] = selected_database_path
    # The notebook reads this target-agnostic alias.
    environment["EQUITY_SENTIMENT_DB_PATH"] = selected_database_path
    return environment


def main() -> None:
    load_dotenv(PROJECT_ROOT / ".env")
    parser = argparse.ArgumentParser(
        description="Run the equity-sentiment workflow from raw inputs through the executed notebook."
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Refresh remote company, OHLC, and news inputs before transforming.",
    )
    parser.add_argument("--days", type=int, default=200)
    parser.add_argument("--news-request-limit", type=int, default=500)
    parser.add_argument("--news-sleep-seconds", type=float, default=1.0)
    parser.add_argument("--ohlc-sleep-seconds", type=float, default=5.0)
    parser.add_argument("--overwrite-ingestion", action="store_true")
    parser.add_argument("--overwrite-transforms", action="store_true")
    parser.add_argument("--skip-factor-download", action="store_true")
    parser.add_argument("--skip-unit-tests", action="store_true")
    parser.add_argument("--skip-notebook", action="store_true")
    parser.add_argument("--skip-dashboard", action="store_true")
    parser.add_argument("--notebook-timeout", type=int, default=300)
    parser.add_argument("--target", choices=["dev", "prod"], default="dev")
    arguments = parser.parse_args()

    environment = build_environment(arguments.target)
    python = sys.executable

    if arguments.ingest:
        run_step(
            "Ingest company metadata",
            [python, str(PROJECT_ROOT / "scripts" / "ingestion" / "crawl_companies.py")],
            environment=environment,
        )

        ohlc_command = [
            python,
            str(PROJECT_ROOT / "scripts" / "ingestion" / "crawl_ohlcs.py"),
            "--days",
            str(arguments.days),
            "--sleep-seconds",
            str(arguments.ohlc_sleep_seconds),
        ]
        news_command = [
            python,
            str(PROJECT_ROOT / "scripts" / "ingestion" / "crawl_news.py"),
            "--days",
            str(arguments.days),
            "--request-limit",
            str(arguments.news_request_limit),
            "--sleep-seconds",
            str(arguments.news_sleep_seconds),
        ]
        if arguments.overwrite_ingestion:
            ohlc_command.append("--overwrite")
            news_command.append("--overwrite")

        run_step("Ingest OHLC prices", ohlc_command, environment=environment)
        run_step("Ingest news", news_command, environment=environment)

    require_local_inputs()

    transform_suffix = ["--overwrite"] if arguments.overwrite_transforms else []
    run_step(
        "Transform company metadata",
        [python, str(PROJECT_ROOT / "scripts" / "transform" / "transform_companies.py")],
        environment=environment,
    )
    run_step(
        "Transform OHLC prices",
        [python, str(PROJECT_ROOT / "scripts" / "transform" / "transform_ohlcs.py"), *transform_suffix],
        environment=environment,
    )
    run_step(
        "Transform news and assign signal dates",
        [python, str(PROJECT_ROOT / "scripts" / "transform" / "transform_news.py"), *transform_suffix],
        environment=environment,
    )

    factor_path = PROJECT_ROOT / "data" / "processed" / "factors" / "fama_french_daily.parquet"
    if not arguments.skip_factor_download:
        run_step(
            "Download Fama-French factors",
            [python, str(PROJECT_ROOT / "scripts" / "ingestion" / "crawl_fama_french_factors.py")],
            environment=environment,
        )
    elif not factor_path.exists():
        raise FileNotFoundError(
            f"--skip-factor-download was used, but {factor_path} does not exist."
        )

    if not arguments.skip_unit_tests:
        run_step(
            "Run Python unit tests",
            [python, "-m", "unittest", "discover", "-s", "tests", "-v"],
            environment=environment,
        )

    dbt_executable = shutil.which("dbt")
    if dbt_executable is None:
        raise RuntimeError("dbt executable not found. Install dependencies from requirements.txt.")
    run_step(
        "Build and test dbt models",
        [
            dbt_executable,
            "build",
            "--target",
            arguments.target,
            "--project-dir",
            str(DBT_PROJECT_DIR),
            "--profiles-dir",
            str(DBT_PROJECT_DIR),
        ],
        cwd=PROJECT_ROOT,
        environment=environment,
    )

    if not arguments.skip_notebook:
        run_step(
            "Execute research notebook",
            [
                python,
                "-m",
                "jupyter",
                "nbconvert",
                "--execute",
                "--to",
                "notebook",
                "--inplace",
                str(NOTEBOOK_PATH),
                f"--ExecutePreprocessor.timeout={arguments.notebook_timeout}",
            ],
            environment=environment,
        )
        run_step(
            "Render research notebook as HTML",
            [
                python,
                "-m",
                "jupyter",
                "nbconvert",
                "--to",
                "html",
                str(NOTEBOOK_PATH),
            ],
            environment=environment,
        )

    if not arguments.skip_dashboard:
        run_step(
            "Synchronize Power BI template and PDF report",
            [
                python,
                str(PROJECT_ROOT / "scripts" / "rebuild_dashboard_artifacts.py"),
                "--database",
                environment["EQUITY_SENTIMENT_DB_PATH"],
            ],
            environment=environment,
        )
        run_step(
            "Generate story-led Power BI dashboard",
            [
                python,
                str(PROJECT_ROOT / "scripts" / "rebuild_powerbi_dashboard.py"),
                "--database",
                environment["EQUITY_SENTIMENT_DB_PATH"],
            ],
            environment=environment,
        )

    print("\nPipeline completed successfully.", flush=True)


if __name__ == "__main__":
    main()
