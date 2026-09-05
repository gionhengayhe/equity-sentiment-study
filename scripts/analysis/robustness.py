from __future__ import annotations

from math import erfc, sqrt
from typing import Iterable

import numpy as np
import pandas as pd


def _normal_two_sided_p(value: float) -> float:
    if not np.isfinite(value):
        return 0.0 if np.isinf(value) else float("nan")
    return float(erfc(abs(value) / sqrt(2.0)))


def _holm_adjust(p_values: Iterable[float]) -> np.ndarray:
    """Holm family-wise error adjustment without an external stats package."""
    p_values = np.asarray(list(p_values), dtype=float)
    order = np.argsort(p_values)
    adjusted_sorted = np.maximum.accumulate(
        np.minimum(1.0, (len(p_values) - np.arange(len(p_values))) * p_values[order])
    )
    adjusted = np.empty_like(adjusted_sorted)
    adjusted[order] = adjusted_sorted
    return adjusted


def _newey_west_covariance(
    design: np.ndarray, residuals: np.ndarray, maxlags: int
) -> np.ndarray:
    """Bartlett-kernel Newey-West covariance for an OLS coefficient vector."""
    scores = design * residuals[:, None]
    meat = scores.T @ scores
    for lag in range(1, maxlags + 1):
        weight = 1.0 - lag / (maxlags + 1.0)
        lag_product = scores[lag:].T @ scores[:-lag]
        meat += weight * (lag_product + lag_product.T)

    inverse_xx = np.linalg.pinv(design.T @ design)
    covariance = inverse_xx @ meat @ inverse_xx
    return (covariance + covariance.T) / 2.0


def _clean_series(values: Iterable[float]) -> np.ndarray:
    return pd.Series(values, dtype="float64").dropna().to_numpy()


def hac_mean(values: Iterable[float], maxlags: int = 5) -> dict[str, float]:
    """Estimate a time-series mean with Newey-West HAC inference."""
    sample = _clean_series(values)
    if len(sample) <= maxlags + 1:
        raise ValueError(f"HAC inference needs more than {maxlags + 1} observations.")

    estimate = float(sample.mean())
    design = np.ones((len(sample), 1))
    covariance = _newey_west_covariance(design, sample - estimate, maxlags)
    standard_error = float(np.sqrt(max(covariance[0, 0], 0.0)))
    statistic = estimate / standard_error if standard_error else np.sign(estimate) * np.inf
    ci_low, ci_high = estimate - 1.96 * standard_error, estimate + 1.96 * standard_error
    return {
        "n_days": int(len(sample)),
        "estimate": estimate,
        "hac_se": standard_error,
        "hac_t": float(statistic),
        "hac_p": _normal_two_sided_p(statistic),
        "hac_ci_low": float(ci_low),
        "hac_ci_high": float(ci_high),
    }


def moving_block_bootstrap_mean(
    values: Iterable[float],
    block_length: int = 5,
    repetitions: int = 5000,
    seed: int = 42,
) -> dict[str, float]:
    """Circular moving-block bootstrap confidence interval for a time-series mean."""
    sample = _clean_series(values)
    if len(sample) < 2:
        raise ValueError("Block bootstrap needs at least two observations.")
    block_length = min(block_length, len(sample))
    block_count = int(np.ceil(len(sample) / block_length))
    rng = np.random.default_rng(seed)
    offsets = np.arange(block_length)
    boot_means = np.empty(repetitions)

    for repetition in range(repetitions):
        starts = rng.integers(0, len(sample), size=block_count)
        indices = ((starts[:, None] + offsets) % len(sample)).ravel()[: len(sample)]
        boot_means[repetition] = sample[indices].mean()

    ci_low, ci_high = np.quantile(boot_means, [0.025, 0.975])
    return {
        "bootstrap_ci_low": float(ci_low),
        "bootstrap_ci_high": float(ci_high),
        "bootstrap_p": float(
            2 * min((boot_means <= 0).mean(), (boot_means >= 0).mean())
        ),
    }


def grouped_inference(
    frame: pd.DataFrame,
    group_column: str,
    value_column: str,
    maxlags: int = 5,
    block_length: int = 5,
    repetitions: int = 5000,
    seed: int = 42,
) -> pd.DataFrame:
    """HAC and block-bootstrap inference for each subgroup's daily return series."""
    rows = []
    for index, (group, group_frame) in enumerate(frame.groupby(group_column, sort=False)):
        inference = hac_mean(group_frame[value_column], maxlags=maxlags)
        inference.update(
            moving_block_bootstrap_mean(
                group_frame[value_column],
                block_length=block_length,
                repetitions=repetitions,
                seed=seed + index,
            )
        )
        inference[group_column] = group
        rows.append(inference)

    result = pd.DataFrame(rows)
    if not result.empty:
        result["hac_p_holm"] = _holm_adjust(result["hac_p"])
    return result


def factor_alpha(
    frame: pd.DataFrame,
    return_column: str,
    factor_columns: list[str],
    maxlags: int = 5,
) -> dict[str, float]:
    """Estimate daily factor alpha with HAC standard errors."""
    regression = frame[[return_column, *factor_columns]].dropna()
    if len(regression) <= len(factor_columns) + maxlags + 1:
        raise ValueError("Not enough observations for factor-adjusted HAC regression.")

    response = regression[return_column].to_numpy(dtype=float)
    design = np.column_stack(
        [np.ones(len(regression)), regression[factor_columns].to_numpy(dtype=float)]
    )
    coefficients = np.linalg.lstsq(design, response, rcond=None)[0]
    residuals = response - design @ coefficients
    covariance = _newey_west_covariance(design, residuals, maxlags)
    standard_error = float(np.sqrt(max(covariance[0, 0], 0.0)))
    statistic = (
        coefficients[0] / standard_error
        if standard_error
        else np.sign(coefficients[0]) * np.inf
    )
    ci_low = float(coefficients[0] - 1.96 * standard_error)
    ci_high = float(coefficients[0] + 1.96 * standard_error)
    total_sum_squares = float(((response - response.mean()) ** 2).sum())
    r_squared = (
        1.0 - float((residuals**2).sum()) / total_sum_squares
        if total_sum_squares
        else float("nan")
    )
    output = {
        "n_days": int(len(regression)),
        "alpha_daily": float(coefficients[0]),
        "alpha_hac_se": standard_error,
        "alpha_hac_t": float(statistic),
        "alpha_hac_p": _normal_two_sided_p(statistic),
        "alpha_ci_low": float(ci_low),
        "alpha_ci_high": float(ci_high),
        "r_squared": r_squared,
    }
    output.update(
        {f"beta_{name}": float(coefficients[index + 1]) for index, name in enumerate(factor_columns)}
    )
    return output


def two_sample_block_bootstrap_difference(
    first: Iterable[float],
    second: Iterable[float],
    block_length: int = 5,
    repetitions: int = 5000,
    seed: int = 42,
) -> dict[str, float]:
    """Bootstrap mean(first) - mean(second) using independent time blocks."""
    first_sample = _clean_series(first)
    second_sample = _clean_series(second)
    if min(len(first_sample), len(second_sample)) < 2:
        raise ValueError("Each sample needs at least two observations.")

    rng = np.random.default_rng(seed)

    def draw_mean(sample: np.ndarray) -> float:
        length = min(block_length, len(sample))
        blocks = int(np.ceil(len(sample) / length))
        starts = rng.integers(0, len(sample), size=blocks)
        indices = ((starts[:, None] + np.arange(length)) % len(sample)).ravel()[: len(sample)]
        return float(sample[indices].mean())

    differences = np.array(
        [draw_mean(first_sample) - draw_mean(second_sample) for _ in range(repetitions)]
    )
    ci_low, ci_high = np.quantile(differences, [0.025, 0.975])
    return {
        "difference": float(first_sample.mean() - second_sample.mean()),
        "bootstrap_ci_low": float(ci_low),
        "bootstrap_ci_high": float(ci_high),
        "bootstrap_p": float(
            2 * min((differences <= 0).mean(), (differences >= 0).mean())
        ),
    }
