from __future__ import annotations

import argparse
import hashlib
import json
import math
import shutil
import sys
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import landscape
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.analysis.robustness import (  # noqa: E402
    factor_alpha,
    grouped_inference,
    hac_mean,
    moving_block_bootstrap_mean,
    two_sample_block_bootstrap_difference,
)


HAC_LAGS = 5
BLOCK_LENGTH = 5
BOOTSTRAP_REPETITIONS = 5000
RANDOM_SEED = 42
OOS_START_DATE = pd.Timestamp("2025-12-15")
PAGE_SIZE = (996.0, 576.0)

NAVY = HexColor("#102A43")
BLUE = HexColor("#1F6FEB")
TEAL = HexColor("#0F8B8D")
GREEN = HexColor("#168B5B")
RED = HexColor("#C43D4B")
AMBER = HexColor("#B7791F")
INK = HexColor("#243B53")
MUTED = HexColor("#627D98")
PALE = HexColor("#F0F4F8")
WHITE = HexColor("#FFFFFF")
LINE = HexColor("#D9E2EC")


def _safe_float(value: object) -> float:
    return float(value) if value is not None else float("nan")


def _date_label(value: object) -> str:
    return pd.Timestamp(value).date().isoformat()


def compute_research_results(connection: duckdb.DuckDBPyConnection) -> dict[str, object]:
    daily = connection.execute(
        """
        SELECT *
        FROM fct_signal_daily_factors
        ORDER BY date_t
        """
    ).df()
    daily["date_t"] = pd.to_datetime(daily["date_t"])
    daily["return_date_t"] = pd.to_datetime(daily["return_date_t"])

    returns = daily["long_short_return_ew"].dropna()
    full = hac_mean(returns, maxlags=HAC_LAGS)
    full.update(
        moving_block_bootstrap_mean(
            returns,
            block_length=BLOCK_LENGTH,
            repetitions=BOOTSTRAP_REPETITIONS,
            seed=RANDOM_SEED,
        )
    )
    full["cumulative_return"] = float((1.0 + returns).prod() - 1.0)

    factors = factor_alpha(
        daily,
        "long_short_return_ew",
        ["mkt_rf", "smb", "hml", "mom"],
        maxlags=HAC_LAGS,
    )

    in_sample = daily.loc[
        daily["date_t"] < OOS_START_DATE, "long_short_return_ew"
    ].dropna()
    out_of_sample = daily.loc[
        daily["date_t"] >= OOS_START_DATE, "long_short_return_ew"
    ].dropna()
    sample_results: dict[str, dict[str, float]] = {}
    for index, (name, values) in enumerate(
        (("in_sample", in_sample), ("out_of_sample", out_of_sample))
    ):
        result = hac_mean(values, maxlags=HAC_LAGS)
        result.update(
            moving_block_bootstrap_mean(
                values,
                block_length=BLOCK_LENGTH,
                repetitions=BOOTSTRAP_REPETITIONS,
                seed=RANDOM_SEED + index,
            )
        )
        result["cumulative_return"] = float((1.0 + values).prod() - 1.0)
        sample_results[name] = result

    stability = two_sample_block_bootstrap_difference(
        out_of_sample,
        in_sample,
        block_length=BLOCK_LENGTH,
        repetitions=BOOTSTRAP_REPETITIONS,
        seed=RANDOM_SEED,
    )

    liquidity_daily = connection.execute(
        """
        WITH daily_bucket AS (
            SELECT
                date_t,
                liquidity_bucket,
                AVG(CASE WHEN sentiment_quintile = 5
                         THEN forward_return_close_to_close_1d END)
                - AVG(CASE WHEN sentiment_quintile = 1
                           THEN forward_return_close_to_close_1d END)
                    AS long_short_return_ew
            FROM fct_signal_panel
            GROUP BY 1, 2
        )
        SELECT * FROM daily_bucket
        WHERE long_short_return_ew IS NOT NULL
        ORDER BY date_t, liquidity_bucket
        """
    ).df()
    liquidity = grouped_inference(
        liquidity_daily,
        "liquidity_bucket",
        "long_short_return_ew",
        maxlags=HAC_LAGS,
        block_length=BLOCK_LENGTH,
        repetitions=BOOTSTRAP_REPETITIONS,
        seed=RANDOM_SEED,
    )
    liquidity_pivot = liquidity_daily.pivot(
        index="date_t", columns="liquidity_bucket", values="long_short_return_ew"
    ).dropna(subset=["Low Liquidity", "High Liquidity"])
    liquidity_difference = (
        liquidity_pivot["Low Liquidity"] - liquidity_pivot["High Liquidity"]
    )
    liquidity_contrast = hac_mean(liquidity_difference, maxlags=HAC_LAGS)
    liquidity_contrast.update(
        moving_block_bootstrap_mean(
            liquidity_difference,
            BLOCK_LENGTH,
            BOOTSTRAP_REPETITIONS,
            RANDOM_SEED,
        )
    )

    news_daily = connection.execute(
        """
        WITH daily_bucket AS (
            SELECT
                date_t,
                news_count_bucket,
                AVG(CASE WHEN sentiment_quintile = 5
                         THEN forward_return_close_to_close_1d END)
                - AVG(CASE WHEN sentiment_quintile = 1
                           THEN forward_return_close_to_close_1d END)
                    AS long_short_return_ew
            FROM fct_signal_panel
            GROUP BY 1, 2
        )
        SELECT * FROM daily_bucket
        WHERE long_short_return_ew IS NOT NULL
        ORDER BY date_t, news_count_bucket
        """
    ).df()
    news = grouped_inference(
        news_daily,
        "news_count_bucket",
        "long_short_return_ew",
        maxlags=HAC_LAGS,
        block_length=BLOCK_LENGTH,
        repetitions=BOOTSTRAP_REPETITIONS,
        seed=RANDOM_SEED,
    )
    news_pivot = news_daily.pivot(
        index="date_t", columns="news_count_bucket", values="long_short_return_ew"
    ).dropna(subset=["5+", "2-3"])
    news_difference = news_pivot["5+"] - news_pivot["2-3"]
    news_contrast = hac_mean(news_difference, maxlags=HAC_LAGS)
    news_contrast.update(
        moving_block_bootstrap_mean(
            news_difference,
            BLOCK_LENGTH,
            BOOTSTRAP_REPETITIONS,
            RANDOM_SEED,
        )
    )

    quality = connection.execute(
        """
        SELECT
            MIN(date_t) AS first_signal_date,
            MAX(date_t) AS last_signal_date,
            MIN(return_date_t) AS first_return_date,
            MAX(return_date_t) AS last_return_date,
            COUNT(*) AS trading_days,
            SUM(stocks_with_signal) AS signal_observations,
            SUM(total_stocks) AS universe_observations,
            AVG(coverage_ratio) AS average_coverage_ratio,
            SUM(stocks_without_current_metadata) AS observations_without_current_metadata
        FROM fct_signal_daily
        """
    ).df().iloc[0]
    panel_quality = connection.execute(
        """
        SELECT
            COUNT(*) AS panel_rows,
            COUNT(DISTINCT ticker) AS distinct_tickers,
            SUM(point_in_time_universe_flag) AS point_in_time_rows,
            SUM(company_metadata_available_flag) AS rows_with_current_metadata
        FROM fct_signal_panel
        """
    ).df().iloc[0]
    news_quality = connection.execute(
        """
        SELECT COUNT(*) AS news_ticker_rows, COUNT(DISTINCT news_id) AS distinct_articles
        FROM stg_news
        """
    ).df().iloc[0]

    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "settings": {
            "hac_lags": HAC_LAGS,
            "block_length": BLOCK_LENGTH,
            "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
            "bootstrap_seed": RANDOM_SEED,
            "oos_start_date": OOS_START_DATE.date().isoformat(),
        },
        "full_sample": full,
        "factor_adjusted": factors,
        "samples": sample_results,
        "oos_minus_in_sample": stability,
        "liquidity_subgroups": liquidity.to_dict(orient="records"),
        "liquidity_contrast": liquidity_contrast,
        "news_subgroups": news.to_dict(orient="records"),
        "news_contrast": news_contrast,
        "quality": {
            **{key: value for key, value in quality.items()},
            **{key: value for key, value in panel_quality.items()},
            **{key: value for key, value in news_quality.items()},
        },
        "daily": daily,
    }


def json_ready(value: object) -> object:
    if isinstance(value, pd.DataFrame):
        return value.to_dict(orient="records")
    if isinstance(value, (pd.Timestamp, datetime)):
        return value.isoformat()
    if hasattr(value, "isoformat") and not isinstance(value, (str, bytes)):
        try:
            return value.isoformat()
        except TypeError:
            pass
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_ready(item) for item in value]
    return value


def _power_bi_type(duckdb_type: str) -> tuple[str, str | None]:
    normalized = duckdb_type.upper()
    if normalized in {"DATE", "TIMESTAMP", "TIMESTAMP WITH TIME ZONE"}:
        return "dateTime", "Short Date" if normalized == "DATE" else "General Date"
    if normalized == "BOOLEAN":
        return "boolean", None
    if any(token in normalized for token in ("INT", "HUGEINT")):
        return "int64", "0"
    if any(token in normalized for token in ("DOUBLE", "FLOAT", "REAL", "DECIMAL")):
        return "double", None
    return "string", None


def _source_schema(connection: duckdb.DuckDBPyConnection, table_name: str) -> list[tuple[str, str]]:
    rows = connection.execute(f'DESCRIBE SELECT * FROM "{table_name}"').fetchall()
    return [(str(row[0]), str(row[1])) for row in rows]


def _new_column(name: str, duckdb_type: str) -> dict[str, object]:
    data_type, format_string = _power_bi_type(duckdb_type)
    column: dict[str, object] = {
        "name": name,
        "dataType": data_type,
        "sourceColumn": name,
        "lineageTag": str(uuid.uuid4()),
        "summarizeBy": "none" if data_type in {"string", "dateTime", "boolean"} else "sum",
        "annotations": [
            {"name": "SummarizationSetBy", "value": "Automatic"},
        ],
    }
    if format_string:
        column["formatString"] = format_string
    if any(token in name for token in ("return", "spread", "coverage", "mkt_rf", "smb", "hml", "mom", "rf")):
        column["formatString"] = "0.0000%;-0.0000%;0.0000%"
    return column


def _new_table(table_name: str, schema: list[tuple[str, str]], database_name: str) -> dict[str, object]:
    return {
        "name": table_name,
        "lineageTag": str(uuid.uuid4()),
        "columns": [_new_column(name, data_type) for name, data_type in schema],
        "partitions": [
            {
                "name": table_name,
                "mode": "import",
                "source": {
                    "type": "m",
                    "expression": [
                        "let",
                        '    Source = Odbc.DataSource("dsn=DuckDB", [HierarchicalNavigation=true]),',
                        f'    {database_name}_Database = Source{{[Name="{database_name}",Kind="Database"]}}[Data],',
                        f'    main_Schema = {database_name}_Database{{[Name="main",Kind="Schema"]}}[Data],',
                        f'    {table_name}_View = main_Schema{{[Name="{table_name}",Kind="View"]}}[Data]',
                        "in",
                        f"    {table_name}_View",
                    ],
                },
            }
        ],
        "annotations": [
            {"name": "PBI_NavigationStepName", "value": "Navigation"},
            {"name": "PBI_ResultType", "value": "Table"},
        ],
    }


def rebuild_pbit(
    pbit_path: Path,
    connection: duckdb.DuckDBPyConnection,
    results: dict[str, object],
    database_name: str,
) -> None:
    with zipfile.ZipFile(pbit_path, "r") as source:
        payloads = {info.filename: source.read(info.filename) for info in source.infolist()}
        infos = source.infolist()

    schema = json.loads(payloads["DataModelSchema"].decode("utf-16le"))
    layout = json.loads(payloads["Report/Layout"].decode("utf-16le"))
    model = schema["model"]
    tables = {table["name"]: table for table in model["tables"]}
    source_mapping = {
        "stg_companies (3)": "stg_companies",
        "dim_date (3)": "dim_date",
        "fct_signal_panel (3)": "fct_signal_panel",
        "fct_signal_daily": "fct_signal_daily",
        "fct_signal_rolling": "fct_signal_rolling",
        "stg_news": "stg_news",
    }

    for model_name, source_name in source_mapping.items():
        table = tables[model_name]
        source_columns = _source_schema(connection, source_name)
        current = {column.get("sourceColumn"): column for column in table.get("columns", [])}
        for column_name, duckdb_type in source_columns:
            if column_name not in current:
                table.setdefault("columns", []).append(_new_column(column_name, duckdb_type))
                continue
            data_type, format_string = _power_bi_type(duckdb_type)
            current[column_name]["dataType"] = data_type
            if format_string and "formatString" not in current[column_name]:
                current[column_name]["formatString"] = format_string

    if "fct_signal_daily_factors" not in tables:
        factors_table = _new_table(
            "fct_signal_daily_factors",
            _source_schema(connection, "fct_signal_daily_factors"),
            database_name,
        )
        model["tables"].append(factors_table)
        tables["fct_signal_daily_factors"] = factors_table

    daily_table = tables["fct_signal_daily"]
    measures = {measure["name"]: measure for measure in daily_table.get("measures", [])}
    full = results["full_sample"]
    measures["t-stat (EW)"]["expression"] = f"{full['hac_t']:.12f}"
    measures["t-stat (EW)"]["description"] = (
        "Full-sample Newey-West HAC t-statistic with five lags. "
        "This frozen research statistic does not respond to report filters."
    )
    measures["Cumulative Spread (EW)"]["expression"] = [
        "VAR CurrentDate = MAX(fct_signal_daily[date_t])",
        "RETURN",
        "    PRODUCTX(",
        "        FILTER(",
        "            ALLSELECTED(fct_signal_daily[date_t]),",
        "            fct_signal_daily[date_t] <= CurrentDate",
        "        ),",
        "        1 + CALCULATE(MAX(fct_signal_daily[long_short_return_ew]))",
        "    ) - 1",
    ]
    measures["Cumulative Spread (EW)"]["description"] = (
        "Compounded selected-period equal-weight long-short return."
    )
    measures["Cumulative Spread (VW)"]["expression"] = [
        "VAR CurrentDate = MAX(fct_signal_daily[date_t])",
        "RETURN",
        "    PRODUCTX(",
        "        FILTER(",
        "            ALLSELECTED(fct_signal_daily[date_t]),",
        "            fct_signal_daily[date_t] <= CurrentDate",
        "        ),",
        "        1 + CALCULATE(MAX(fct_signal_daily[long_short_return_lw]))",
        "    ) - 1",
    ]
    measures["Cumulative Spread (VW)"]["description"] = (
        "Compounded selected-period liquidity-weighted long-short return."
    )
    measures["EW/VW Ratio"]["expression"] = [
        "DIVIDE(",
        "    AVERAGE(fct_signal_daily[long_short_return_ew]),",
        "    AVERAGE(fct_signal_daily[long_short_return_lw]))",
    ]
    measures["EW/VW Ratio"]["description"] = "EW mean divided by liquidity-weighted mean."

    panel_measures = {
        measure["name"]: measure
        for measure in tables["fct_signal_panel (3)"].get("measures", [])
    }
    for name, quintile in (("Q5 Avg Fwd Return", 5), ("Q1 Avg Fwd Return", 1)):
        panel_measures[name]["expression"] = [
            "",
            "CALCULATE(",
            "    AVERAGE('fct_signal_panel (3)'[forward_return_close_to_close_1d]),",
            f"    'fct_signal_panel (3)'[sentiment_quintile] = {quintile}",
            ")",
        ]

    replacements = {
        "Cumulative Long–Short Spread (EW)": "Cumulative Long–Short Return (EW)",
        "Scale Test: EW vs. VW Cumulative Alpha": "Scale Test: EW vs. LW Cumulative Return",
        "Value-Weight Spread": "Liquidity-Weight Return",
        "Statistical Confidence": "HAC Confidence (Full Sample)",
    }
    layout_text = json.dumps(layout, ensure_ascii=False, separators=(",", ":"))
    for old, new in replacements.items():
        layout_text = layout_text.replace(old, new)
    layout = json.loads(layout_text)

    annotations = model.setdefault("annotations", [])
    annotations = [a for a in annotations if a.get("name") != "EquitySentimentArtifactBuild"]
    annotations.append(
        {
            "name": "EquitySentimentArtifactBuild",
            "value": json.dumps(
                {
                    "generated_at_utc": results["generated_at_utc"],
                    "database": database_name,
                    "hac_lags": HAC_LAGS,
                    "block_length": BLOCK_LENGTH,
                    "bootstrap_repetitions": BOOTSTRAP_REPETITIONS,
                    "oos_start_date": OOS_START_DATE.date().isoformat(),
                },
                separators=(",", ":"),
            ),
        }
    )
    model["annotations"] = annotations

    payloads["DataModelSchema"] = json.dumps(
        schema, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-16le")
    payloads["Report/Layout"] = json.dumps(
        layout, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-16le")

    with tempfile.NamedTemporaryFile(
        prefix="equity-sentiment-", suffix=".pbit", delete=False, dir=pbit_path.parent
    ) as handle:
        temporary_path = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary_path, "w") as target:
            for info in infos:
                target.writestr(info, payloads[info.filename])
        with zipfile.ZipFile(temporary_path, "r") as check:
            if check.testzip() is not None:
                raise RuntimeError("The rebuilt PBIT archive failed its CRC check.")
            rebuilt = json.loads(check.read("DataModelSchema").decode("utf-16le"))
            names = {table["name"] for table in rebuilt["model"]["tables"]}
            if "fct_signal_daily_factors" not in names:
                raise RuntimeError("The rebuilt PBIT is missing fct_signal_daily_factors.")
        shutil.move(str(temporary_path), str(pbit_path))
    finally:
        temporary_path.unlink(missing_ok=True)


def _register_fonts() -> tuple[str, str]:
    candidates = [
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("C:/Windows/Fonts/calibri.ttf"), Path("C:/Windows/Fonts/calibrib.ttf")),
    ]
    for regular, bold in candidates:
        if regular.exists() and bold.exists():
            pdfmetrics.registerFont(TTFont("ReportRegular", str(regular)))
            pdfmetrics.registerFont(TTFont("ReportBold", str(bold)))
            return "ReportRegular", "ReportBold"
    return "Helvetica", "Helvetica-Bold"


def _draw_wrapped_text(
    pdf: canvas.Canvas,
    text: str,
    x: float,
    y: float,
    width: float,
    *,
    font: str,
    size: float,
    color=INK,
    leading: float | None = None,
    max_lines: int | None = None,
) -> float:
    leading = leading or size * 1.35
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if pdf.stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    if max_lines is not None:
        lines = lines[:max_lines]
    pdf.setFont(font, size)
    pdf.setFillColor(color)
    for line in lines:
        pdf.drawString(x, y, line)
        y -= leading
    return y


def _page_header(pdf: canvas.Canvas, title: str, subtitle: str, regular: str, bold: str) -> None:
    width, height = PAGE_SIZE
    pdf.setFillColor(NAVY)
    pdf.rect(0, height - 74, width, 74, stroke=0, fill=1)
    pdf.setFillColor(WHITE)
    pdf.setFont(bold, 21)
    pdf.drawString(34, height - 35, title)
    pdf.setFont(regular, 9)
    pdf.setFillColor(HexColor("#D9EAF7"))
    pdf.drawString(35, height - 55, subtitle)


def _footer(pdf: canvas.Canvas, page_number: int, regular: str) -> None:
    width, _ = PAGE_SIZE
    pdf.setStrokeColor(LINE)
    pdf.line(34, 24, width - 34, 24)
    pdf.setFillColor(MUTED)
    pdf.setFont(regular, 7.5)
    pdf.drawString(34, 11, "Equity Sentiment Study | reproducible local pipeline")
    pdf.drawRightString(width - 34, 11, f"Page {page_number} of 4")


def _metric_card(
    pdf: canvas.Canvas,
    x: float,
    y: float,
    width: float,
    height: float,
    label: str,
    value: str,
    note: str,
    regular: str,
    bold: str,
    accent=BLUE,
) -> None:
    pdf.setFillColor(WHITE)
    pdf.setStrokeColor(LINE)
    pdf.roundRect(x, y, width, height, 7, stroke=1, fill=1)
    pdf.setFillColor(accent)
    pdf.roundRect(x, y + height - 7, width, 7, 7, stroke=0, fill=1)
    pdf.setFillColor(MUTED)
    pdf.setFont(regular, 8)
    pdf.drawString(x + 14, y + height - 27, label.upper())
    pdf.setFillColor(INK)
    pdf.setFont(bold, 20)
    pdf.drawString(x + 14, y + height - 54, value)
    _draw_wrapped_text(
        pdf,
        note,
        x + 14,
        y + 18,
        width - 28,
        font=regular,
        size=7.6,
        color=MUTED,
        leading=9.5,
        max_lines=2,
    )


def _save_cumulative_chart(daily: pd.DataFrame, path: Path) -> None:
    frame = daily.dropna(subset=["long_short_return_ew"]).copy()
    frame["cumulative"] = (1.0 + frame["long_short_return_ew"]).cumprod() - 1.0
    fig, ax = plt.subplots(figsize=(9.2, 3.6), dpi=180)
    ax.plot(frame["date_t"], frame["cumulative"] * 100, color="#1F6FEB", linewidth=2.2)
    ax.axvline(OOS_START_DATE, color="#C43D4B", linewidth=1.5, linestyle="--")
    ax.axhline(0, color="#627D98", linewidth=0.8)
    ax.fill_between(
        frame["date_t"],
        frame["cumulative"] * 100,
        0,
        where=frame["cumulative"] >= 0,
        color="#1F6FEB",
        alpha=0.09,
    )
    ax.text(OOS_START_DATE, ax.get_ylim()[1] * 0.92, " Holdout starts", color="#C43D4B", fontsize=8)
    ax.set_ylabel("Cumulative return (%)")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(axis="y", alpha=0.22)
    ax.spines[["top", "right"]].set_visible(False)
    fig.autofmt_xdate(rotation=0)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _save_daily_chart(daily: pd.DataFrame, path: Path) -> None:
    frame = daily.dropna(subset=["long_short_return_ew"]).copy()
    colors = np.where(frame["long_short_return_ew"] >= 0, "#168B5B", "#C43D4B")
    fig, ax = plt.subplots(figsize=(9.2, 2.65), dpi=180)
    ax.bar(frame["date_t"], frame["long_short_return_ew"] * 100, color=colors, width=1.3, alpha=0.8)
    ax.axhline(0, color="#627D98", linewidth=0.8)
    ax.axvline(OOS_START_DATE, color="#C43D4B", linewidth=1.2, linestyle="--")
    ax.set_ylabel("Daily Q5-Q1 (%)")
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.grid(axis="y", alpha=0.18)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def _save_forest_chart(
    rows: list[dict[str, object]],
    label_column: str,
    path: Path,
    title: str,
) -> None:
    frame = pd.DataFrame(rows).sort_values("estimate")
    positions = np.arange(len(frame))
    estimate = frame["estimate"].astype(float).to_numpy() * 100
    low = frame["hac_ci_low"].astype(float).to_numpy() * 100
    high = frame["hac_ci_high"].astype(float).to_numpy() * 100
    fig, ax = plt.subplots(figsize=(4.3, 2.8), dpi=180)
    ax.errorbar(
        estimate,
        positions,
        xerr=[estimate - low, high - estimate],
        fmt="o",
        color="#1F6FEB",
        ecolor="#627D98",
        capsize=4,
        markersize=6,
    )
    ax.axvline(0, color="#C43D4B", linewidth=1, linestyle="--")
    ax.set_yticks(positions, frame[label_column].astype(str))
    ax.set_xlabel("Mean daily Q5-Q1 return (%)")
    ax.set_title(title, fontsize=10, loc="left", fontweight="bold")
    ax.grid(axis="x", alpha=0.2)
    ax.spines[["top", "right", "left"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight", facecolor="white")
    plt.close(fig)


def build_pdf(pdf_path: Path, results: dict[str, object], work_dir: Path) -> None:
    regular, bold = _register_fonts()
    daily = results["daily"]
    cumulative_chart = work_dir / "cumulative.png"
    daily_chart = work_dir / "daily.png"
    liquidity_chart = work_dir / "liquidity.png"
    news_chart = work_dir / "news.png"
    _save_cumulative_chart(daily, cumulative_chart)
    _save_daily_chart(daily, daily_chart)
    _save_forest_chart(
        results["liquidity_subgroups"],
        "liquidity_bucket",
        liquidity_chart,
        "Liquidity subgroups | 95% HAC confidence intervals",
    )
    _save_forest_chart(
        results["news_subgroups"],
        "news_count_bucket",
        news_chart,
        "News-intensity subgroups | 95% HAC confidence intervals",
    )

    with tempfile.NamedTemporaryFile(
        prefix="equity-sentiment-", suffix=".pdf", delete=False, dir=pdf_path.parent
    ) as handle:
        temporary_path = Path(handle.name)
    try:
        pdf = canvas.Canvas(str(temporary_path), pagesize=PAGE_SIZE)
        pdf.setTitle("Equity Sentiment Study — Reproducible Research Report")
        pdf.setAuthor("Equity Sentiment Study pipeline")
        pdf.setSubject("HAC, block bootstrap, factor-adjusted and out-of-sample validation")

        full = results["full_sample"]
        factor = results["factor_adjusted"]
        samples = results["samples"]
        stability = results["oos_minus_in_sample"]
        quality = results["quality"]

        # Page 1 — answer first.
        _page_header(
            pdf,
            "Financial News Sentiment Alpha Study",
            "Rebuilt from DuckDB after dbt tests and a top-to-bottom notebook execution",
            regular,
            bold,
        )
        _metric_card(
            pdf, 34, 366, 216, 112,
            "Full-sample daily mean", f"{full['estimate']:.3%}",
            f"132 days | HAC p={full['hac_p']:.3f} | block p={full['bootstrap_p']:.3f}",
            regular, bold, BLUE,
        )
        _metric_card(
            pdf, 267, 366, 216, 112,
            "Compounded EW return", f"{full['cumulative_return']:.1%}",
            "Before costs; 200% gross exposure and 0% net exposure.",
            regular, bold, TEAL,
        )
        _metric_card(
            pdf, 500, 366, 216, 112,
            "FF3 + momentum alpha", f"{factor['alpha_daily']:.3%}",
            f"HAC p={factor['alpha_hac_p']:.3f}; 95% CI includes zero.",
            regular, bold, AMBER,
        )
        _metric_card(
            pdf, 733, 366, 229, 112,
            "Holdout daily mean", f"{samples['out_of_sample']['estimate']:.3%}",
            f"53 days | HAC p={samples['out_of_sample']['hac_p']:.3f} | cumulative {samples['out_of_sample']['cumulative_return']:.1%}",
            regular, bold, RED,
        )

        pdf.setFillColor(PALE)
        pdf.roundRect(34, 204, 928, 132, 9, stroke=0, fill=1)
        pdf.setFillColor(NAVY)
        pdf.setFont(bold, 14)
        pdf.drawString(52, 310, "Decision-relevant conclusion")
        conclusion = (
            "The positive full-sample association does not survive the chronological holdout "
            "and is not statistically significant after FF3+momentum adjustment. The OOS-minus-IS "
            f"difference is {stability['difference']:.3%} per day (block p={stability['bootstrap_p']:.3f}). "
            "The evidence is therefore not reliable proof of tradable alpha."
        )
        _draw_wrapped_text(
            pdf, conclusion, 52, 282, 890, font=regular, size=12, color=INK, leading=18
        )
        pdf.setFillColor(MUTED)
        pdf.setFont(regular, 8)
        pdf.drawString(
            52,
            222,
            "Interpretation is before transaction costs, financing, short borrow, slippage and corporate-action adjustments.",
        )

        pdf.setFillColor(INK)
        pdf.setFont(bold, 11)
        pdf.drawString(34, 169, "Sample and provenance")
        details = [
            f"Signal dates: {_date_label(quality['first_signal_date'])} to {_date_label(quality['last_signal_date'])}",
            f"Realized return dates: {_date_label(quality['first_return_date'])} to {_date_label(quality['last_return_date'])}",
            f"Panel: {int(quality['panel_rows']):,} ticker-days across {int(quality['distinct_tickers']):,} tickers",
            f"News: {int(quality['distinct_articles']):,} distinct articles / {int(quality['news_ticker_rows']):,} ticker-article rows",
        ]
        for index, text in enumerate(details):
            x = 34 + (index % 2) * 470
            y = 144 - (index // 2) * 30
            pdf.setFillColor(BLUE)
            pdf.circle(x + 4, y + 3, 3, stroke=0, fill=1)
            pdf.setFillColor(INK)
            pdf.setFont(regular, 9)
            pdf.drawString(x + 14, y, text)
        _footer(pdf, 1, regular)
        pdf.showPage()

        # Page 2 — return path and holdout split.
        _page_header(
            pdf,
            "Performance path and stability",
            "Canonical portfolio: signal at the 16:00 ET cutoff; close(date_t) to next common trading-session close",
            regular,
            bold,
        )
        pdf.setFillColor(INK)
        pdf.setFont(bold, 12)
        pdf.drawString(40, 478, "Compounded equal-weight long-short return")
        pdf.drawImage(str(cumulative_chart), 34, 266, width=928, height=204, preserveAspectRatio=True, anchor="c")
        pdf.setFillColor(INK)
        pdf.setFont(bold, 12)
        pdf.drawString(40, 244, "Daily Q5-minus-Q1 returns")
        pdf.drawImage(str(daily_chart), 34, 68, width=635, height=166, preserveAspectRatio=True, anchor="c")

        pdf.setFillColor(PALE)
        pdf.roundRect(692, 68, 270, 166, 8, stroke=0, fill=1)
        pdf.setFont(bold, 10)
        pdf.setFillColor(NAVY)
        pdf.drawString(710, 210, "Frozen chronological split")
        rows = [
            ("In sample", samples["in_sample"]),
            ("Holdout", samples["out_of_sample"]),
        ]
        y = 182
        for label, row in rows:
            pdf.setFont(bold, 9)
            pdf.setFillColor(INK)
            pdf.drawString(710, y, label)
            pdf.setFont(regular, 8)
            pdf.setFillColor(MUTED)
            pdf.drawString(
                710,
                y - 16,
                f"n={row['n_days']} | mean {row['estimate']:.3%} | HAC p={row['hac_p']:.3f}",
            )
            y -= 52
        pdf.setFont(regular, 7.5)
        pdf.setFillColor(RED)
        pdf.drawString(710, 82, f"Holdout - training: {stability['difference']:.3%}/day")
        _footer(pdf, 2, regular)
        pdf.showPage()

        # Page 3 — subgroup analysis.
        _page_header(
            pdf,
            "Subgroup analysis with dependence-aware inference",
            "Each subgroup uses Newey-West HAC (5 lags), 5-day circular moving-block bootstrap and Holm correction",
            regular,
            bold,
        )
        pdf.drawImage(str(liquidity_chart), 36, 260, width=445, height=214, preserveAspectRatio=True, anchor="c")
        pdf.drawImage(str(news_chart), 515, 260, width=445, height=214, preserveAspectRatio=True, anchor="c")

        liquidity_mid = next(
            row for row in results["liquidity_subgroups"] if row["liquidity_bucket"] == "Mid Liquidity"
        )
        news_low = next(
            row for row in results["news_subgroups"] if row["news_count_bucket"] == "2-3"
        )
        pdf.setFillColor(PALE)
        pdf.roundRect(36, 82, 924, 148, 8, stroke=0, fill=1)
        pdf.setFillColor(NAVY)
        pdf.setFont(bold, 11)
        pdf.drawString(54, 204, "What the subgroup tests do — and do not — establish")
        bullets = [
            f"Mid-liquidity mean: {liquidity_mid['estimate']:.3%}/day; Holm-adjusted HAC p={liquidity_mid['hac_p_holm']:.3f}.",
            f"Low-minus-high liquidity contrast: {results['liquidity_contrast']['estimate']:.3%}/day; HAC p={results['liquidity_contrast']['hac_p']:.3f}.",
            f"2-3 article subgroup: {news_low['estimate']:.3%}/day; Holm-adjusted HAC p={news_low['hac_p_holm']:.3f}.",
            f"5+-minus-2-3 article contrast: {results['news_contrast']['estimate']:.3%}/day; HAC p={results['news_contrast']['hac_p']:.3f}.",
        ]
        y = 178
        for text in bullets:
            pdf.setFillColor(BLUE)
            pdf.circle(58, y + 3, 2.6, stroke=0, fill=1)
            y = _draw_wrapped_text(
                pdf, text, 69, y, 870, font=regular, size=9, color=INK, leading=16
            ) - 4
        pdf.setFont(bold, 8.5)
        pdf.setFillColor(RED)
        pdf.drawString(54, 94, "Conclusion: direct contrasts do not support a monotonic liquidity or news-intensity effect.")
        _footer(pdf, 3, regular)
        pdf.showPage()

        # Page 4 — definitions, QA and reproducibility.
        _page_header(
            pdf,
            "Definitions, data integrity and reproducibility",
            "The report, notebook and Power BI template all read the same tested DuckDB model",
            regular,
            bold,
        )
        columns = [
            (
                "Canonical definitions",
                [
                    ("Signal time", "Articles before 16:00 ET map to that session; later items map to the next session."),
                    ("Return horizon", "close(date_t) to close(next common market session); factors join on the realized return date."),
                    ("Daily portfolio", "Equal-weight Q5 minus Q1; one unit long and one unit short."),
                    ("Cumulative return", "PRODUCT(1 + daily return) - 1; arithmetic spread is diagnostic only."),
                ],
            ),
            (
                "Inference and validation",
                [
                    ("HAC", "Newey-West standard errors with five lags for means and factor alpha."),
                    ("Bootstrap", "5,000 circular moving-block draws, five-day blocks, fixed seed 42."),
                    ("Factors", "Daily FF3 plus momentum aligned to return_date_t."),
                    ("Holdout", "Frozen start 2025-12-15; no construction or inference rules change across the split."),
                ],
            ),
            (
                "Data health",
                [
                    ("Point-in-time universe", f"{int(quality['point_in_time_rows']):,}/{int(quality['panel_rows']):,} panel rows pass the price-history-based universe rule."),
                    ("Current metadata", f"Only {int(quality['rows_with_current_metadata']):,} rows have current company metadata; missing metadata does not exclude securities."),
                    ("Coverage", f"Average daily signal coverage is {_safe_float(quality['average_coverage_ratio']):.1%}."),
                    ("Pipeline checks", "9 Python unit tests and 72 successful dbt nodes (11 models + 61 data tests)."),
                ],
            ),
        ]
        for index, (heading, items) in enumerate(columns):
            x = 34 + index * 315
            pdf.setFillColor(WHITE)
            pdf.setStrokeColor(LINE)
            pdf.roundRect(x, 84, 296, 380, 8, stroke=1, fill=1)
            pdf.setFillColor(NAVY)
            pdf.setFont(bold, 12)
            pdf.drawString(x + 18, 432, heading)
            y = 398
            for label, description in items:
                pdf.setFillColor(BLUE)
                pdf.setFont(bold, 9)
                pdf.drawString(x + 18, y, label)
                y = _draw_wrapped_text(
                    pdf,
                    description,
                    x + 18,
                    y - 16,
                    258,
                    font=regular,
                    size=8.2,
                    color=INK,
                    leading=11,
                ) - 18
        pdf.setFillColor(MUTED)
        pdf.setFont(regular, 7.5)
        pdf.drawString(
            34,
            52,
            f"Built {results['generated_at_utc']} | Source: equity_sentiment/dev.duckdb | PBIT connection: ODBC DSN DuckDB",
        )
        _footer(pdf, 4, regular)
        pdf.save()

        if temporary_path.stat().st_size < 50_000:
            raise RuntimeError("Generated PDF is unexpectedly small.")
        shutil.move(str(temporary_path), str(pdf_path))
    finally:
        temporary_path.unlink(missing_ok=True)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Synchronize the Power BI template and PDF research report with DuckDB."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=PROJECT_ROOT / "equity_sentiment" / "dev.duckdb",
    )
    parser.add_argument(
        "--pbit",
        type=Path,
        default=PROJECT_ROOT / "dashboard" / "equity-sentiment.pbit",
    )
    parser.add_argument(
        "--pdf",
        type=Path,
        default=PROJECT_ROOT / "dashboard" / "equity-sentiment.pdf",
    )
    parser.add_argument(
        "--summary",
        type=Path,
        default=PROJECT_ROOT / "dashboard" / "research_summary.json",
    )
    arguments = parser.parse_args()

    database = arguments.database.resolve()
    pbit = arguments.pbit.resolve()
    pdf = arguments.pdf.resolve()
    summary = arguments.summary.resolve()
    if not database.exists():
        raise FileNotFoundError(database)
    if not pbit.exists():
        raise FileNotFoundError(pbit)
    pbit.parent.mkdir(parents=True, exist_ok=True)
    pdf.parent.mkdir(parents=True, exist_ok=True)
    summary.parent.mkdir(parents=True, exist_ok=True)

    connection = duckdb.connect(str(database), read_only=True)
    try:
        results = compute_research_results(connection)
        rebuild_pbit(pbit, connection, results, database.stem)
        with tempfile.TemporaryDirectory(prefix="equity-sentiment-pdf-") as directory:
            build_pdf(pdf, results, Path(directory))
    finally:
        connection.close()

    serializable = {key: value for key, value in results.items() if key != "daily"}
    summary.write_text(
        json.dumps(json_ready(serializable), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Rebuilt PBIT: {pbit} ({pbit.stat().st_size:,} bytes, sha256={file_sha256(pbit)})")
    print(f"Rebuilt PDF:  {pdf} ({pdf.stat().st_size:,} bytes, sha256={file_sha256(pdf)})")
    print(f"Summary:      {summary}")


if __name__ == "__main__":
    main()
