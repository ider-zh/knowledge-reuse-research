"""Compare a descending empirical rank curve with fixed reference shapes."""

from __future__ import annotations

import math
from typing import Any

import numpy as np


def first_n_primes(count: int) -> np.ndarray:
    """Return the first ``count`` primes with a deterministic sieve."""

    if count < 0:
        raise ValueError("prime count must be non-negative")
    if count == 0:
        return np.array([], dtype=np.int64)
    upper = 15 if count < 6 else math.ceil(
        count * (math.log(count) + math.log(math.log(count)))
    ) + 10
    while True:
        sieve = np.ones(upper + 1, dtype=bool)
        sieve[:2] = False
        for prime in range(2, math.isqrt(upper) + 1):
            if sieve[prime]:
                sieve[prime * prime :: prime] = False
        primes = np.flatnonzero(sieve)
        if primes.size >= count:
            return primes[:count]
        upper *= 2


def _display_ranks(population_size: int, limit: int = 280) -> list[int]:
    if population_size <= limit:
        return list(range(1, population_size + 1))
    return sorted(
        {
            1,
            population_size,
            *(
                round(math.exp(math.log(population_size) * index / (limit - 1)))
                for index in range(limit)
            ),
        }
    )


def _shape_fit(log10_values: np.ndarray, log10_base: np.ndarray) -> dict[str, float]:
    """Fit amplitude for exponent one, then estimate an unconstrained exponent."""

    fixed_intercept = float(np.mean(log10_values + log10_base))
    fixed_prediction = fixed_intercept - log10_base
    fixed_residual = log10_values - fixed_prediction
    centered = log10_values - float(np.mean(log10_values))
    total_sum_squares = float(centered @ centered)
    residual_sum_squares = float(fixed_residual @ fixed_residual)

    base_centered = log10_base - float(np.mean(log10_base))
    denominator = float(base_centered @ base_centered)
    slope = float((base_centered @ centered) / denominator)
    free_beta = -slope
    free_intercept = float(np.mean(log10_values) - slope * np.mean(log10_base))
    free_prediction = free_intercept + slope * log10_base
    free_residual = log10_values - free_prediction
    free_residual_sum_squares = float(free_residual @ free_residual)

    return {
        "fixed_intercept_log10": fixed_intercept,
        "fixed_rmse_log10": math.sqrt(residual_sum_squares / log10_values.size),
        "fixed_mae_log10": float(np.mean(np.abs(fixed_residual))),
        "fixed_r_squared_log10": (
            1.0 - residual_sum_squares / total_sum_squares
            if total_sum_squares > 0
            else 1.0
        ),
        "free_exponent_beta": free_beta,
        "free_intercept_log10": free_intercept,
        "free_rmse_log10": math.sqrt(free_residual_sum_squares / log10_values.size),
        "free_r_squared_log10": (
            1.0 - free_residual_sum_squares / total_sum_squares
            if total_sum_squares > 0
            else 1.0
        ),
    }


def compare_rank_reference_curves(log10_values: np.ndarray) -> dict[str, Any]:
    """Compare path-count ranks with ``1/r`` and reciprocal exact-prime ranks.

    The input contains base-10 logarithms of positive counts.  Two ranges are
    reported: all positive observations and the highest-count one percent.
    Both fixed templates receive one fitted amplitude, so their log-space RMSE
    and R-squared values are directly comparable.
    """

    values = np.asarray(log10_values, dtype=float)
    values = np.sort(values[np.isfinite(values)])[::-1]
    if values.size < 20:
        raise ValueError("rank-shape comparison requires at least 20 positive values")
    primes = first_n_primes(int(values.size)).astype(float)
    top_one_percent = max(20, math.ceil(values.size * 0.01))
    ranges = []
    for range_id, count in (
        ("all_positive", int(values.size)),
        ("top_1pct", top_one_percent),
    ):
        observed = values[:count]
        ranks = np.arange(1, count + 1, dtype=float)
        range_primes = primes[:count]
        log10_rank = np.log10(ranks)
        log10_prime = np.log10(range_primes)
        zipf = _shape_fit(observed, log10_rank)
        reciprocal_prime = _shape_fit(observed, log10_prime)
        display_ranks = _display_ranks(count)
        points = []
        for rank in display_ranks:
            index = rank - 1
            points.append(
                {
                    "rank": rank,
                    "log10_rank": float(log10_rank[index]),
                    "empirical_log10": float(observed[index]),
                    "zipf_log10": float(
                        zipf["fixed_intercept_log10"] - log10_rank[index]
                    ),
                    "reciprocal_prime_log10": float(
                        reciprocal_prime["fixed_intercept_log10"] - log10_prime[index]
                    ),
                    "free_rank_fit_log10": float(
                        zipf["free_intercept_log10"]
                        - zipf["free_exponent_beta"] * log10_rank[index]
                    ),
                }
            )
        ranges.append(
            {
                "range_id": range_id,
                "observation_count": count,
                "maximum_log10": float(observed[0]),
                "minimum_log10": float(observed[-1]),
                "models": {
                    "zipf": {
                        "formula": "P(r)=10^a/r",
                        **zipf,
                    },
                    "reciprocal_prime": {
                        "formula": "P(r)=10^a/p_r, where p_r is the exact r-th prime",
                        **reciprocal_prime,
                    },
                },
                "display_point_count": len(points),
                "points": points,
            }
        )
    return {
        "metric": "in_paths_source_log10",
        "positive_observation_count": int(values.size),
        "comparison_space": "ordinary least squares in log10(path count) space",
        "amplitude_policy": "one independently fitted intercept per fixed reference",
        "prime_transform": (
            "the prime-counting and nth-prime curves increase; reciprocal exact nth-prime "
            "values provide a decreasing rank-shape reference"
        ),
        "ranges": ranges,
    }
