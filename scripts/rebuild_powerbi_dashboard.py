from __future__ import annotations

import argparse
import copy
import json
import shutil
import sys
import tempfile
import uuid
import zipfile
from pathlib import Path

import duckdb
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.rebuild_dashboard_artifacts import compute_research_results  # noqa: E402


PAGE_WIDTH = 1280.0
PAGE_HEIGHT = 720.0
INK = "#19324D"
NAVY = "#0B1F33"
BLUE = "#2474E8"
TEAL = "#169C9C"
AMBER = "#D89A22"
RED = "#C84C5A"
SLATE = "#6B7C93"
PALE = "#F4F7FB"
SOFT_BLUE = "#EAF2FF"
WHITE = "#FFFFFF"
LINE = "#D9E3EF"


SUMMARY_MEASURES = {
    "Full Sample Mean": ("full_sample", "estimate", "0.000%;-0.000%;0.000%"),
    "Full Sample HAC p-value": ("full_sample", "hac_p", "0.0000"),
    "Full Sample Cumulative Return": (
        "full_sample",
        "cumulative_return",
        "0.0%;-0.0%;0.0%",
    ),
    "Factor Adjusted Alpha": ("factor_adjusted", "alpha_daily", "0.000%;-0.000%;0.000%"),
    "Factor Alpha HAC p-value": ("factor_adjusted", "alpha_hac_p", "0.0000"),
    "In Sample Mean": ("samples.in_sample", "estimate", "0.000%;-0.000%;0.000%"),
    "Holdout Mean": ("samples.out_of_sample", "estimate", "0.000%;-0.000%;0.000%"),
    "Holdout HAC p-value": ("samples.out_of_sample", "hac_p", "0.0000"),
    "OOS Minus IS": ("oos_minus_in_sample", "difference", "0.000%;-0.000%;0.000%"),
    "OOS-IS Bootstrap p-value": ("oos_minus_in_sample", "bootstrap_p", "0.0000"),
}


def _nested_value(results: dict[str, object], path: str, key: str) -> float:
    value: object = results
    for part in path.split("."):
        value = value[part]  # type: ignore[index]
    return float(value[key])  # type: ignore[index]


def _literal(value: str) -> dict[str, object]:
    return {"expr": {"Literal": {"Value": value}}}


def _color(value: str) -> dict[str, object]:
    return {"solid": {"color": _literal(f"'{value}'")}}


def _set_position(
    visual: dict[str, object], x: float, y: float, width: float, height: float, z: int
) -> dict[str, object]:
    visual["x"] = x
    visual["y"] = y
    visual["z"] = z
    visual["width"] = width
    visual["height"] = height
    config = json.loads(str(visual["config"]))
    config["name"] = uuid.uuid4().hex[:20]
    position = config["layouts"][0]["position"]
    position.update(
        {
            "x": x,
            "y": y,
            "z": z,
            "width": width,
            "height": height,
            "tabOrder": z,
        }
    )
    visual["config"] = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
    return visual


def _set_title(visual: dict[str, object], title: str) -> None:
    config = json.loads(str(visual["config"]))
    single = config["singleVisual"]
    objects = single.setdefault("vcObjects", {})
    objects["title"] = [
        {
            "properties": {
                "show": _literal("true"),
                "text": _literal(f"'{title}'"),
                "titleWrap": _literal("true"),
                "alignment": _literal("'left'"),
                "fontSize": _literal("12D"),
                "bold": _literal("true"),
                "italic": _literal("false"),
                "fontColor": _color(INK),
            }
        }
    ]
    visual["config"] = json.dumps(config, ensure_ascii=False, separators=(",", ":"))


def _set_visual_type(visual: dict[str, object], visual_type: str) -> None:
    config = json.loads(str(visual["config"]))
    config["singleVisual"]["visualType"] = visual_type
    visual["config"] = json.dumps(config, ensure_ascii=False, separators=(",", ":"))


def _style_visual(visual: dict[str, object], *, accent: str = LINE) -> None:
    config = json.loads(str(visual["config"]))
    single = config["singleVisual"]
    vc = single.setdefault("vcObjects", {})
    vc["background"] = [
        {
            "properties": {
                "show": _literal("true"),
                "color": _color(WHITE),
                "transparency": _literal("0D"),
            }
        }
    ]
    vc["border"] = [
        {
            "properties": {
                "show": _literal("true"),
                "color": _color(accent),
                "width": _literal("1D"),
                "radius": _literal("12D"),
            }
        }
    ]
    vc["dropShadow"] = [{"properties": {"show": _literal("true")}}]
    vc["visualHeader"] = [{"properties": {"show": _literal("false")}}]
    if single.get("visualType") == "card":
        single.setdefault("objects", {})["categoryLabels"] = [
            {
                "properties": {
                    "show": _literal("true"),
                    "color": _color(SLATE),
                    "fontSize": _literal("10D"),
                }
            }
        ]
        single["objects"]["labels"] = [
            {
                "properties": {
                    "fontSize": _literal("22D"),
                    "bold": _literal("true"),
                    "color": _color(accent if accent != LINE else BLUE),
                }
            }
        ]
    visual["config"] = json.dumps(config, ensure_ascii=False, separators=(",", ":"))


def _strip_stale_date_filters(visual: dict[str, object]) -> None:
    visual["filters"] = "[]"
    if not visual.get("query"):
        return
    query = json.loads(str(visual["query"]))
    for command in query.get("Commands", []):
        semantic = command.get("SemanticQueryDataShapeCommand", {})
        inner = semantic.get("Query", {})
        where = inner.get("Where", [])
        retained = []
        for item in where:
            serialized = json.dumps(item, separators=(",", ":"))
            is_stale_date_range = (
                '"Property":"date_t"' in serialized
                and "datetime'2025-11-03" in serialized
            )
            if not is_stale_date_range:
                retained.append(item)
        if retained:
            inner["Where"] = retained
        else:
            inner.pop("Where", None)
    visual["query"] = json.dumps(query, ensure_ascii=False, separators=(",", ":"))


def _clone_visual(
    source: dict[str, object],
    x: float,
    y: float,
    width: float,
    height: float,
    z: int,
    *,
    title: str | None = None,
    accent: str = LINE,
) -> dict[str, object]:
    visual = copy.deepcopy(source)
    _set_position(visual, x, y, width, height, z)
    _strip_stale_date_filters(visual)
    _style_visual(visual, accent=accent)
    if title is not None:
        _set_title(visual, title)
    return visual


def _replace_visual_text(visual: dict[str, object], replacements: dict[str, str]) -> None:
    for key in ("config", "query", "dataTransforms"):
        if not visual.get(key):
            continue
        text = str(visual[key])
        for old, new in replacements.items():
            text = text.replace(old, new)
        visual[key] = text


def _measure_card(
    source: dict[str, object],
    measure: str,
    title: str,
    x: float,
    y: float,
    width: float,
    height: float,
    z: int,
    accent: str,
) -> dict[str, object]:
    visual = copy.deepcopy(source)
    _replace_visual_text(
        visual,
        {
            "t-stat (EW)": measure,
            "HAC Confidence (Full Sample)": title,
        },
    )
    _set_position(visual, x, y, width, height, z)
    _strip_stale_date_filters(visual)
    _style_visual(visual, accent=accent)
    _set_title(visual, title)
    return visual


def _textbox(
    source: dict[str, object],
    paragraphs: list[tuple[str, str, str, str]],
    x: float,
    y: float,
    width: float,
    height: float,
    z: int,
    *,
    background: str | None = None,
    border: str | None = None,
) -> dict[str, object]:
    visual = copy.deepcopy(source)
    _set_position(visual, x, y, width, height, z)
    config = json.loads(str(visual["config"]))
    single = config["singleVisual"]
    runs = []
    for text, size, color, weight in paragraphs:
        runs.append(
            {
                "textRuns": [
                    {
                        "value": text,
                        "textStyle": {
                            "fontWeight": weight,
                            "fontSize": size,
                            "color": color,
                        },
                    }
                ]
            }
        )
    single["objects"] = {"general": [{"properties": {"paragraphs": runs}}]}
    vc = single.setdefault("vcObjects", {})
    vc["visualHeader"] = [{"properties": {"show": _literal("false")}}]
    if background:
        vc["background"] = [
            {
                "properties": {
                    "show": _literal("true"),
                    "color": _color(background),
                    "transparency": _literal("0D"),
                }
            }
        ]
    else:
        vc["background"] = [{"properties": {"show": _literal("false")}}]
    if border:
        vc["border"] = [
            {
                "properties": {
                    "show": _literal("true"),
                    "color": _color(border),
                    "width": _literal("1D"),
                    "radius": _literal("12D"),
                }
            }
        ]
    else:
        vc["border"] = [{"properties": {"show": _literal("false")}}]
    visual["config"] = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
    visual["filters"] = "[]"
    visual.pop("query", None)
    visual.pop("dataTransforms", None)
    return visual


def _page_header(source: dict[str, object], number: str, title: str, subtitle: str) -> dict[str, object]:
    return _textbox(
        source,
        [
            (f"{number}  /  {title}", "24pt", NAVY, "bold"),
            (subtitle, "10pt", SLATE, "normal"),
        ],
        24,
        14,
        920,
        76,
        0,
    )


def _page_config() -> str:
    return json.dumps(
        {
            "objects": {
                "outspace": [{"properties": {"color": _color("#E7EDF5")}}],
                "background": [
                    {
                        "properties": {
                            "color": _color(PALE),
                            "transparency": _literal("0D"),
                        }
                    }
                ],
                "outspacePane": [{"properties": {}}],
            }
        },
        separators=(",", ":"),
    )


def _upsert_measures(model: dict[str, object], results: dict[str, object]) -> None:
    tables = {table["name"]: table for table in model["tables"]}  # type: ignore[index]
    daily = tables["fct_signal_daily"]
    measures = {measure["name"]: measure for measure in daily.setdefault("measures", [])}
    for name, (path, key, format_string) in SUMMARY_MEASURES.items():
        value = _nested_value(results, path, key)
        measure = measures.get(name)
        if measure is None:
            measure = {
                "name": name,
                "lineageTag": str(uuid.uuid4()),
            }
            daily["measures"].append(measure)
            measures[name] = measure
        measure.update(
            {
                "expression": f"{value:.15g}",
                "formatString": format_string,
                "displayFolder": "Research Summary",
                "description": "Frozen result from the synchronized research pipeline.",
            }
        )

    quality = results["quality"]
    constant_quality = {
        "Panel Rows": (int(quality["panel_rows"]), "#,0"),
        "Distinct Tickers": (int(quality["distinct_tickers"]), "#,0"),
        "Distinct Articles": (int(quality["distinct_articles"]), "#,0"),
    }
    for name, (value, format_string) in constant_quality.items():
        measure = measures.get(name)
        if measure is None:
            measure = {"name": name, "lineageTag": str(uuid.uuid4())}
            daily["measures"].append(measure)
            measures[name] = measure
        measure.update(
            {
                "expression": str(value),
                "formatString": format_string,
                "displayFolder": "Data Quality",
                "description": "Frozen count from the synchronized research pipeline.",
            }
        )

    coverage = measures.get("Average Coverage")
    if coverage is None:
        coverage = {"name": "Average Coverage", "lineageTag": str(uuid.uuid4())}
        daily["measures"].append(coverage)
    coverage.update(
        {
            "expression": "AVERAGE(fct_signal_daily[coverage_ratio])",
            "formatString": "0.0%",
            "displayFolder": "Data Quality",
            "description": "Average daily share of point-in-time universe stocks with a qualifying signal.",
        }
    )


def _custom_theme(original: bytes) -> bytes:
    theme = json.loads(original.decode("utf-8-sig"))
    theme.update(
        {
            "dataColors": [BLUE, TEAL, AMBER, "#7B8BA4", RED],
            "foreground": INK,
            "foregroundNeutralSecondary": SLATE,
            "foregroundNeutralTertiary": LINE,
            "background": WHITE,
            "backgroundLight": PALE,
            "backgroundNeutral": LINE,
            "tableAccent": BLUE,
            "good": TEAL,
            "neutral": AMBER,
            "bad": RED,
            "maximum": BLUE,
            "center": "#B8C6D9",
            "minimum": SOFT_BLUE,
        }
    )
    text_classes = theme.setdefault("textClasses", {})
    text_classes["callout"] = {"fontSize": 24, "fontFace": "Segoe UI Semibold", "color": INK}
    text_classes["title"] = {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": INK}
    text_classes["header"] = {"fontSize": 11, "fontFace": "Segoe UI Semibold", "color": INK}
    text_classes["label"] = {"fontSize": 9, "fontFace": "Segoe UI", "color": SLATE}
    return json.dumps(theme, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def rebuild_report_layout(
    layout: dict[str, object], results: dict[str, object]
) -> dict[str, object]:
    original_pages = layout["sections"]
    expected_pages = [
        "01 Executive Overview",
        "02 Robustness & Holdout",
        "03 Data Quality & Method",
    ]
    if [page.get("displayName") for page in original_pages] == expected_pages:
        overview, validation, data_quality = original_pages
        # Refresh the two visuals whose chart contracts changed after the first
        # generated version. This branch also makes repeated pipeline runs safe.
        news = _clone_visual(
            validation["visualContainers"][10],
            836,
            468,
            420,
            226,
            32,
            title="Daily Q5-Q1 return by news intensity",
            accent=LINE,
        )
        _replace_visual_text(
            news,
            {
                "liquidity_bucket": "news_count_bucket",
                "Liquidity": "News intensity",
                "liquidity": "news intensity",
            },
        )
        _set_visual_type(validation["visualContainers"][10], "clusteredBarChart")
        _set_visual_type(news, "clusteredBarChart")
        validation["visualContainers"][11] = news
        _set_visual_type(data_quality["visualContainers"][7], "lineChart")
        for page in original_pages:
            page["filters"] = "[]"
            page["config"] = _page_config()
            for visual in page["visualContainers"]:
                _strip_stale_date_filters(visual)
        return layout

    if len(original_pages) != 4:
        raise RuntimeError(
            "Expected either the four-page legacy template or the three-page generated dashboard; "
            f"found {[page.get('displayName') for page in original_pages]}."
        )
    p1, p2, p3, p4 = original_pages
    base_card = p1["visualContainers"][3]
    base_textbox = p3["visualContainers"][10]

    cumulative = _clone_visual(
        p1["visualContainers"][5], 24, 236, 760, 310, 20,
        title="Compounded long-short return | equal weight", accent=LINE,
    )
    quintile = _clone_visual(
        p1["visualContainers"][6], 804, 236, 452, 310, 21,
        title="Next-session return by sentiment quintile", accent=LINE,
    )
    _replace_visual_text(
        quintile,
        {
            "forward_return_1d": "forward_return_close_to_close_1d",
            "1-Day Return": "Next-session return",
        },
    )

    overview = copy.deepcopy(p1)
    overview.update(
        {
            "displayName": "01 Executive Overview",
            "ordinal": 0,
            "filters": "[]",
            "config": _page_config(),
            "visualContainers": [
                _page_header(
                    base_textbox,
                    "01",
                    "EXECUTIVE OVERVIEW",
                    "Does financial-news sentiment produce robust next-session alpha?  |  Full-sample KPI cards; slicer controls charts.",
                ),
                _clone_visual(p1["visualContainers"][8], 976, 24, 280, 66, 1, accent=LINE),
                _measure_card(base_card, "Full Sample Mean", "Daily Q5-Q1 mean", 24, 108, 222, 110, 2, BLUE),
                _measure_card(base_card, "Full Sample Cumulative Return", "Compounded EW return", 264, 108, 222, 110, 3, TEAL),
                _measure_card(base_card, "Full Sample HAC p-value", "HAC p-value", 504, 108, 222, 110, 4, AMBER),
                _measure_card(base_card, "Factor Alpha HAC p-value", "Factor-adjusted p", 744, 108, 222, 110, 5, AMBER),
                _measure_card(base_card, "Holdout Mean", "Holdout daily mean", 984, 108, 272, 110, 6, RED),
                cumulative,
                quintile,
                _textbox(
                    base_textbox,
                    [
                        ("VERDICT  |  FULL-SAMPLE ASSOCIATION, NOT RELIABLE TRADABLE ALPHA", "13pt", NAVY, "bold"),
                        (
                            "The 0.236% daily mean is borderline under HAC and block bootstrap, but factor-adjusted alpha is insignificant and the 53-day holdout mean is -0.027%. Read the 34.1% compounded return as an in-sample path before costs—not as an implementation forecast.",
                            "10pt",
                            INK,
                            "normal",
                        ),
                        ("Signal cutoff 16:00 ET  •  close-to-next-common-session horizon  •  200% gross / 0% net  •  before trading and borrow costs", "9pt", SLATE, "normal"),
                    ],
                    24,
                    566,
                    1232,
                    130,
                    30,
                    background=SOFT_BLUE,
                    border="#C8DAF3",
                ),
            ],
        }
    )

    rolling = _clone_visual(
        p4["visualContainers"][0], 24, 228, 610, 220, 20,
        title="Rolling 20-day mean return", accent=LINE,
    )
    _replace_visual_text(
        rolling,
        {
            "fct_signal_daily": "fct_signal_rolling",
            "coverage_ratio": "spread_mean_20d",
            "Coverage ratio": "Rolling 20-day mean",
            "Coverage Ratio": "Rolling 20-day mean",
        },
    )
    scale = _clone_visual(
        p3["visualContainers"][0], 654, 228, 602, 220, 21,
        title="Compounded return | EW versus liquidity weight", accent=LINE,
    )
    sector = _clone_visual(
        p2["visualContainers"][3], 24, 468, 386, 226, 30,
        title="Daily Q5-Q1 return by sector", accent=LINE,
    )
    liquidity = _clone_visual(
        p2["visualContainers"][4], 430, 468, 386, 226, 31,
        title="Daily Q5-Q1 return by liquidity", accent=LINE,
    )
    _set_visual_type(liquidity, "clusteredBarChart")
    news = _clone_visual(
        p2["visualContainers"][4], 836, 468, 420, 226, 32,
        title="Daily Q5-Q1 return by news intensity", accent=LINE,
    )
    _replace_visual_text(
        news,
        {
            "liquidity_bucket": "news_count_bucket",
            "Liquidity": "News intensity",
            "liquidity": "news intensity",
        },
    )
    _set_visual_type(news, "clusteredBarChart")

    validation = copy.deepcopy(p2)
    validation.update(
        {
            "displayName": "02 Robustness & Holdout",
            "ordinal": 1,
            "filters": "[]",
            "config": _page_config(),
            "visualContainers": [
                _page_header(
                    base_textbox,
                    "02",
                    "ROBUSTNESS & HOLDOUT",
                    "HAC (5 lags), 5-day circular block bootstrap, FF3+momentum and a frozen 15 Dec 2025 holdout.",
                ),
                _measure_card(base_card, "Factor Adjusted Alpha", "Factor alpha", 24, 108, 182, 100, 2, BLUE),
                _measure_card(base_card, "Factor Alpha HAC p-value", "Factor p-value", 226, 108, 182, 100, 3, AMBER),
                _measure_card(base_card, "In Sample Mean", "Training mean", 428, 108, 182, 100, 4, TEAL),
                _measure_card(base_card, "Holdout Mean", "Holdout mean", 630, 108, 182, 100, 5, RED),
                _measure_card(base_card, "OOS Minus IS", "Holdout - training", 832, 108, 182, 100, 6, RED),
                _measure_card(base_card, "OOS-IS Bootstrap p-value", "Difference p-value", 1034, 108, 222, 100, 7, AMBER),
                rolling,
                scale,
                sector,
                liquidity,
                news,
            ],
        }
    )

    coverage = _clone_visual(
        p4["visualContainers"][0], 24, 230, 600, 220, 20,
        title="Signal coverage over time", accent=LINE,
    )
    universe = _clone_visual(
        p4["visualContainers"][1], 644, 230, 612, 220, 21,
        title="Daily eligible universe with qualifying signals", accent=LINE,
    )
    _set_visual_type(universe, "lineChart")
    table = _clone_visual(
        p4["visualContainers"][3], 24, 470, 762, 224, 30,
        title="Coverage diagnostics by signal date", accent=LINE,
    )
    data_quality = copy.deepcopy(p3)
    data_quality.update(
        {
            "displayName": "03 Data Quality & Method",
            "ordinal": 2,
            "filters": "[]",
            "config": _page_config(),
            "visualContainers": [
                _page_header(
                    base_textbox,
                    "03",
                    "DATA QUALITY & METHOD",
                    "Coverage is a research constraint, not a performance KPI. Current metadata never filters the historical price universe.",
                ),
                _clone_visual(p1["visualContainers"][8], 976, 24, 280, 66, 1, accent=LINE),
                _measure_card(base_card, "Average Coverage", "Average signal coverage", 24, 108, 285, 100, 2, BLUE),
                _measure_card(base_card, "Panel Rows", "Panel ticker-days", 329, 108, 285, 100, 3, TEAL),
                _measure_card(base_card, "Distinct Tickers", "Distinct tickers", 634, 108, 285, 100, 4, BLUE),
                _measure_card(base_card, "Distinct Articles", "Distinct articles", 939, 108, 317, 100, 5, TEAL),
                coverage,
                universe,
                table,
                _textbox(
                    base_textbox,
                    [
                        ("CANONICAL METHOD", "12pt", NAVY, "bold"),
                        ("Signal  •  news before 16:00 ET maps to the same close; later news maps forward.", "9pt", INK, "normal"),
                        ("Return  •  close(date_t) to the next common market-session close.", "9pt", INK, "normal"),
                        ("Portfolio  •  equal-weight Q5 minus Q1; compounded as PRODUCT(1+r)-1.", "9pt", INK, "normal"),
                        ("Universe  •  point-in-time price history; current company metadata is enrichment only.", "9pt", INK, "normal"),
                        ("KNOWN LIMITS", "11pt", RED, "bold"),
                        ("No point-in-time security-type master, delisting returns, transaction costs, borrow availability or corporate-action validation.", "9pt", INK, "normal"),
                    ],
                    806,
                    470,
                    450,
                    224,
                    31,
                    background=WHITE,
                    border=LINE,
                ),
            ],
        }
    )

    layout["sections"] = [overview, validation, data_quality]
    return layout


def rebuild_pbit(pbit_path: Path, results: dict[str, object]) -> None:
    with zipfile.ZipFile(pbit_path, "r") as source:
        infos = source.infolist()
        payloads = {item.filename: source.read(item.filename) for item in infos}

    schema = json.loads(payloads["DataModelSchema"].decode("utf-16le"))
    layout = json.loads(payloads["Report/Layout"].decode("utf-16le"))
    _upsert_measures(schema["model"], results)
    layout = rebuild_report_layout(layout, results)

    payloads["DataModelSchema"] = json.dumps(
        schema, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-16le")
    payloads["Report/Layout"] = json.dumps(
        layout, ensure_ascii=False, separators=(",", ":")
    ).encode("utf-16le")
    theme_path = "Report/StaticResources/SharedResources/BaseThemes/CY26SU02.json"
    payloads[theme_path] = _custom_theme(payloads[theme_path])

    with tempfile.NamedTemporaryFile(
        prefix="equity-sentiment-dashboard-",
        suffix=".pbit",
        delete=False,
        dir=pbit_path.parent,
    ) as handle:
        temporary = Path(handle.name)
    try:
        with zipfile.ZipFile(temporary, "w") as target:
            for info in infos:
                target.writestr(info, payloads[info.filename])
        with zipfile.ZipFile(temporary, "r") as check:
            if check.testzip() is not None:
                raise RuntimeError("Rebuilt PBIT failed its CRC check.")
            check_layout = json.loads(check.read("Report/Layout").decode("utf-16le"))
            page_names = [page["displayName"] for page in check_layout["sections"]]
            if page_names != [
                "01 Executive Overview",
                "02 Robustness & Holdout",
                "03 Data Quality & Method",
            ]:
                raise RuntimeError(f"Unexpected dashboard pages: {page_names}")
        shutil.move(str(temporary), str(pbit_path))
    finally:
        temporary.unlink(missing_ok=True)


def _add_panel(fig: plt.Figure, left: float, bottom: float, width: float, height: float) -> None:
    fig.patches.append(
        FancyBboxPatch(
            (left, bottom),
            width,
            height,
            boxstyle="round,pad=0.004,rounding_size=0.012",
            transform=fig.transFigure,
            facecolor=WHITE,
            edgecolor=LINE,
            linewidth=0.9,
            zorder=-5,
        )
    )


def _preview_header(fig: plt.Figure, number: str, title: str, subtitle: str) -> None:
    fig.text(0.035, 0.94, f"{number}  /  {title}", fontsize=19, fontweight="bold", color=NAVY)
    fig.text(0.035, 0.905, subtitle, fontsize=8.5, color=SLATE)


def _preview_card(
    fig: plt.Figure,
    left: float,
    width: float,
    label: str,
    value: str,
    accent: str,
    note: str = "",
) -> None:
    _add_panel(fig, left, 0.735, width, 0.125)
    fig.patches.append(
        FancyBboxPatch(
            (left, 0.849), width, 0.011,
            boxstyle="round,pad=0,rounding_size=0.006",
            transform=fig.transFigure, facecolor=accent, edgecolor=accent, zorder=-4,
        )
    )
    fig.text(left + 0.014, 0.823, label.upper(), fontsize=7.4, color=SLATE)
    fig.text(left + 0.014, 0.768, value, fontsize=17, fontweight="bold", color=INK)
    if note:
        fig.text(left + 0.014, 0.746, note, fontsize=6.6, color=SLATE)


def _chart_axes(fig: plt.Figure, rect: tuple[float, float, float, float], title: str) -> plt.Axes:
    left, bottom, width, height = rect
    _add_panel(fig, left, bottom, width, height)
    fig.text(left + 0.015, bottom + height - 0.034, title, fontsize=10, fontweight="bold", color=INK)
    ax = fig.add_axes([left + 0.045, bottom + 0.052, width - 0.07, height - 0.105])
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#B8C6D9")
    ax.tick_params(labelsize=7, colors=SLATE)
    ax.grid(axis="y", color=LINE, linewidth=0.7, alpha=0.75)
    ax.set_axisbelow(True)
    return ax


def _new_preview(path: Path) -> plt.Figure:
    fig = plt.figure(figsize=(12.8, 7.2), dpi=150, facecolor=PALE)
    return fig


def build_previews(
    output_dir: Path,
    connection: duckdb.DuckDBPyConnection,
    results: dict[str, object],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    daily = results["daily"].copy()
    daily["date_t"] = pd.to_datetime(daily["date_t"])
    full = results["full_sample"]
    factor = results["factor_adjusted"]
    samples = results["samples"]
    stability = results["oos_minus_in_sample"]

    quintiles = connection.execute(
        """
        SELECT sentiment_quintile,
               AVG(forward_return_close_to_close_1d) AS mean_return
        FROM fct_signal_panel
        GROUP BY 1 ORDER BY 1
        """
    ).df()
    rolling = connection.execute(
        "SELECT date_t, spread_mean_20d FROM fct_signal_rolling ORDER BY date_t"
    ).df()
    rolling["date_t"] = pd.to_datetime(rolling["date_t"])
    sectors = connection.execute(
        """
        SELECT sector,
               AVG(CASE WHEN sentiment_quintile=5 THEN forward_return_close_to_close_1d END)
               - AVG(CASE WHEN sentiment_quintile=1 THEN forward_return_close_to_close_1d END)
                   AS mean_return
        FROM fct_signal_panel
        WHERE sector IS NOT NULL
        GROUP BY 1 ORDER BY mean_return
        """
    ).df()

    # Page 1.
    fig = _new_preview(output_dir / "01-executive-overview.png")
    _preview_header(
        fig,
        "01",
        "EXECUTIVE OVERVIEW",
        "Does financial-news sentiment produce robust next-session alpha?  |  Signal dates 18 Aug 2025 - 3 Mar 2026",
    )
    card_width = 0.176
    for left, label, value, accent, note in [
        (0.035, "Daily Q5-Q1 mean", f"{full['estimate']:.3%}", BLUE, f"HAC p={full['hac_p']:.3f}"),
        (0.226, "Compounded EW return", f"{full['cumulative_return']:.1%}", TEAL, "before costs"),
        (0.417, "HAC p-value", f"{full['hac_p']:.4f}", AMBER, "5 Newey-West lags"),
        (0.608, "Factor-adjusted p", f"{factor['alpha_hac_p']:.4f}", AMBER, f"alpha {factor['alpha_daily']:.3%}"),
        (0.799, "Holdout daily mean", f"{samples['out_of_sample']['estimate']:.3%}", RED, f"p={samples['out_of_sample']['hac_p']:.3f}"),
    ]:
        _preview_card(fig, left, card_width, label, value, accent, note)

    ax = _chart_axes(fig, (0.035, 0.285, 0.605, 0.405), "Compounded long-short return | equal weight")
    cumulative = (1 + daily["long_short_return_ew"]).cumprod() - 1
    ax.plot(daily["date_t"], cumulative * 100, color=BLUE, linewidth=2.1)
    ax.fill_between(daily["date_t"], cumulative * 100, 0, color=BLUE, alpha=0.09)
    ax.axvline(pd.Timestamp("2025-12-15"), color=RED, linestyle="--", linewidth=1.1)
    ax.set_ylabel("Cumulative return (%)", fontsize=7, color=SLATE)
    ax.xaxis.set_major_locator(mdates.MonthLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))

    ax = _chart_axes(fig, (0.66, 0.285, 0.305, 0.405), "Next-session return by sentiment quintile")
    ax.bar(quintiles["sentiment_quintile"].astype(str), quintiles["mean_return"] * 100, color=BLUE, alpha=0.88)
    ax.axhline(0, color=SLATE, linewidth=0.8)
    ax.set_ylabel("Mean return (%)", fontsize=7, color=SLATE)

    _add_panel(fig, 0.035, 0.055, 0.93, 0.18)
    fig.text(0.055, 0.19, "VERDICT  |  FULL-SAMPLE ASSOCIATION, NOT RELIABLE TRADABLE ALPHA", fontsize=10.5, fontweight="bold", color=NAVY)
    fig.text(
        0.055,
        0.135,
        "The 0.236% daily mean is borderline under HAC and block bootstrap, but factor-adjusted alpha is insignificant\n"
        "and the holdout mean is -0.027%. The 34.1% compounded path is an in-sample result before costs.",
        fontsize=8.6,
        color=INK,
        linespacing=1.5,
    )
    fig.text(0.055, 0.078, "16:00 ET cutoff  •  next common-session close  •  200% gross / 0% net  •  no trading or borrow costs", fontsize=7.2, color=SLATE)
    fig.savefig(output_dir / "01-executive-overview.png", bbox_inches="tight", facecolor=PALE)
    plt.close(fig)

    # Page 2.
    fig = _new_preview(output_dir / "02-robustness-holdout.png")
    _preview_header(fig, "02", "ROBUSTNESS & HOLDOUT", "Dependence-aware inference, factor adjustment and a frozen 15 Dec 2025 holdout")
    for left, label, value, accent, note in [
        (0.035, "Factor alpha", f"{factor['alpha_daily']:.3%}", BLUE, f"p={factor['alpha_hac_p']:.3f}"),
        (0.194, "Factor p-value", f"{factor['alpha_hac_p']:.4f}", AMBER, "HAC, 5 lags"),
        (0.353, "Training mean", f"{samples['in_sample']['estimate']:.3%}", TEAL, "79 days"),
        (0.512, "Holdout mean", f"{samples['out_of_sample']['estimate']:.3%}", RED, "53 days"),
        (0.671, "Holdout - training", f"{stability['difference']:.3%}", RED, "percentage points/day"),
        (0.830, "Difference p-value", f"{stability['bootstrap_p']:.4f}", AMBER, "5-day block bootstrap"),
    ]:
        _preview_card(fig, left, 0.145, label, value, accent, note)

    ax = _chart_axes(fig, (0.035, 0.42, 0.455, 0.27), "Rolling 20-day mean return")
    ax.plot(rolling["date_t"], rolling["spread_mean_20d"] * 100, color=BLUE, linewidth=1.8)
    ax.axhline(0, color=SLATE, linewidth=0.8)
    ax.set_ylabel("Q5-Q1 (%)", fontsize=7, color=SLATE)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))

    ax = _chart_axes(fig, (0.51, 0.42, 0.455, 0.27), "Compounded return | EW versus liquidity weight")
    ax.plot(daily["date_t"], daily["cumulative_return_ew"] * 100, color=BLUE, linewidth=1.8, label="EW")
    ax.plot(daily["date_t"], daily["cumulative_return_lw"] * 100, color=TEAL, linewidth=1.6, linestyle="--", label="LW")
    ax.legend(frameon=False, fontsize=7, loc="upper left")
    ax.set_ylabel("Cumulative return (%)", fontsize=7, color=SLATE)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))

    for rect, title, labels, values in [
        ((0.035, 0.055, 0.285, 0.31), "Daily Q5-Q1 return by sector", sectors["sector"], sectors["mean_return"]),
        ((0.34, 0.055, 0.285, 0.31), "Daily Q5-Q1 return by liquidity", [row["liquidity_bucket"] for row in results["liquidity_subgroups"]], [row["estimate"] for row in results["liquidity_subgroups"]]),
        ((0.645, 0.055, 0.32, 0.31), "Daily Q5-Q1 return by news intensity", [row["news_count_bucket"] for row in results["news_subgroups"]], [row["estimate"] for row in results["news_subgroups"]]),
    ]:
        ax = _chart_axes(fig, rect, title)
        values_array = np.asarray(values, dtype=float) * 100
        positions = np.arange(len(values_array))
        ax.barh(positions, values_array, color=BLUE, alpha=0.85)
        ax.set_yticks(positions, [str(label) for label in labels])
        ax.axvline(0, color=SLATE, linewidth=0.8)
        ax.set_xlabel("Mean daily return (%)", fontsize=7, color=SLATE)
    fig.savefig(output_dir / "02-robustness-holdout.png", bbox_inches="tight", facecolor=PALE)
    plt.close(fig)

    # Page 3.
    quality = results["quality"]
    fig = _new_preview(output_dir / "03-data-quality-method.png")
    _preview_header(fig, "03", "DATA QUALITY & METHOD", "Coverage constrains interpretation; current metadata never filters the historical price universe")
    for left, label, value, accent, note in [
        (0.035, "Average coverage", f"{float(quality['average_coverage_ratio']):.1%}", BLUE, "daily qualifying signals"),
        (0.274, "Panel ticker-days", f"{int(quality['panel_rows']):,}", TEAL, "point-in-time price universe"),
        (0.513, "Distinct tickers", f"{int(quality['distinct_tickers']):,}", BLUE, "historical price tape"),
        (0.752, "Distinct articles", f"{int(quality['distinct_articles']):,}", TEAL, "deduplicated news IDs"),
    ]:
        _preview_card(fig, left, 0.213, label, value, accent, note)

    ax = _chart_axes(fig, (0.035, 0.405, 0.455, 0.285), "Signal coverage over time")
    ax.plot(daily["date_t"], daily["coverage_ratio"] * 100, color=BLUE, linewidth=1.7)
    ax.fill_between(daily["date_t"], daily["coverage_ratio"] * 100, 0, color=BLUE, alpha=0.08)
    ax.set_ylabel("Coverage (%)", fontsize=7, color=SLATE)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))

    ax = _chart_axes(fig, (0.51, 0.405, 0.455, 0.285), "Daily eligible universe with qualifying signals")
    ax.plot(daily["date_t"], daily["stocks_with_signal"], color=TEAL, linewidth=1.7)
    ax.set_ylabel("Stocks", fontsize=7, color=SLATE)
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))

    _add_panel(fig, 0.035, 0.055, 0.58, 0.30)
    fig.text(0.055, 0.315, "Latest coverage diagnostics", fontsize=10, fontweight="bold", color=INK)
    latest = daily.tail(6).iloc[::-1]
    columns = ["Signal date", "Coverage", "With signal", "Universe", "Missing prices"]
    xs = [0.055, 0.19, 0.31, 0.435, 0.535]
    for x, label in zip(xs, columns):
        fig.text(x, 0.275, label, fontsize=7, fontweight="bold", color=SLATE)
    for row_index, (_, row) in enumerate(latest.iterrows()):
        y = 0.242 - row_index * 0.032
        values = [
            pd.Timestamp(row["date_t"]).strftime("%d %b %Y"),
            f"{row['coverage_ratio']:.1%}",
            f"{int(row['stocks_with_signal']):,}",
            f"{int(row['total_stocks']):,}",
            f"{int(row['missing_price_count']):,}",
        ]
        for x, value in zip(xs, values):
            fig.text(x, y, value, fontsize=7, color=INK)

    _add_panel(fig, 0.635, 0.055, 0.33, 0.30)
    fig.text(0.655, 0.315, "Canonical method", fontsize=10, fontweight="bold", color=INK)
    method_lines = [
        "Signal  •  pre-16:00 ET news maps to the same close",
        "Return  •  close(date_t) to next common-session close",
        "Portfolio  •  equal-weight Q5 minus Q1; 200% gross",
        "Cumulative  •  PRODUCT(1 + daily return) - 1",
        "Universe  •  price-history based; metadata enrichment only",
        "Limits  •  no costs, borrow, delisting or PIT security master",
    ]
    for index, text in enumerate(method_lines):
        fig.text(0.655, 0.275 - index * 0.036, text, fontsize=7.2, color=INK if index < 5 else RED)
    fig.savefig(output_dir / "03-data-quality-method.png", bbox_inches="tight", facecolor=PALE)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a story-led Power BI research dashboard from code.")
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
        "--preview-dir",
        type=Path,
        default=PROJECT_ROOT / "dashboard" / "previews",
    )
    arguments = parser.parse_args()

    database = arguments.database.resolve()
    pbit = arguments.pbit.resolve()
    preview_dir = arguments.preview_dir.resolve()
    connection = duckdb.connect(str(database), read_only=True)
    try:
        results = compute_research_results(connection)
        rebuild_pbit(pbit, results)
        build_previews(preview_dir, connection, results)
    finally:
        connection.close()

    print(f"Rebuilt story-led PBIT: {pbit}")
    print(f"Rendered previews: {preview_dir}")


if __name__ == "__main__":
    main()
