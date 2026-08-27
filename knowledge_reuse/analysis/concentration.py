"""Source-neutral concentration metrics for non-negative reuse counts."""

from __future__ import annotations

import math

import numpy as np


def gini(values: np.ndarray) -> float:
    data = np.asarray(values, dtype=float)
    if data.size == 0 or data.sum() == 0:
        return 0.0
    data = np.sort(data)
    n = data.size
    return float(
        (2 * np.dot(np.arange(1, n + 1), data) / (n * data.sum())) - (n + 1) / n
    )


def hhi(values: np.ndarray) -> float:
    data = np.asarray(values, dtype=float)
    total = data.sum()
    return float(np.square(data / total).sum()) if total else 0.0


def top_share(values: np.ndarray, fraction: float) -> float:
    if not 0 < fraction <= 1:
        raise ValueError("fraction must be in (0, 1]")
    data = np.asarray(values, dtype=float)
    if data.size == 0 or data.sum() == 0:
        return 0.0
    count = max(1, math.ceil(data.size * fraction))
    return float(np.sort(data)[-count:].sum() / data.sum())
