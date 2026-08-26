from __future__ import annotations

import math
import contextlib
import io
import warnings
from typing import Any

import numpy as np
import powerlaw


def fit_tail(values: np.ndarray, population: str) -> dict[str, Any]:
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data) & (data > 0)]
    if data.size < 20 or np.unique(data).size < 3:
        return {
            "population": population,
            "n": int(data.size),
            "status": "insufficient_positive_observations",
            "xmin": None,
            "alpha": None,
            "ks": None,
            "bootstrap_p": None,
            "bootstrap_status": "not_implemented_v1",
            "powerlaw_vs_lognormal_r": None,
            "powerlaw_vs_lognormal_p": None,
            "powerlaw_vs_truncated_r": None,
            "powerlaw_vs_truncated_p": None,
        }
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore")
        fit = powerlaw.Fit(data, discrete=True, verbose=False)
        lognormal_r, lognormal_p = fit.distribution_compare(
            "power_law", "lognormal", normalized_ratio=True
        )
        truncated_r, truncated_p = fit.distribution_compare(
            "power_law", "truncated_power_law", normalized_ratio=True
        )
    values_to_check = (
        fit.xmin,
        fit.power_law.alpha,
        fit.power_law.D,
        lognormal_r,
        lognormal_p,
        truncated_r,
        truncated_p,
    )
    if not all(math.isfinite(float(value)) for value in values_to_check):
        status = "fit_contains_nonfinite_values"
    else:
        status = "ok"
    return {
        "population": population,
        "n": int(data.size),
        "tail_n": int(np.count_nonzero(data >= fit.xmin)),
        "status": status,
        "xmin": float(fit.xmin),
        "alpha": float(fit.power_law.alpha),
        "ks": float(fit.power_law.D),
        "bootstrap_p": None,
        "bootstrap_status": "not_implemented_v1",
        "powerlaw_vs_lognormal_r": float(lognormal_r),
        "powerlaw_vs_lognormal_p": float(lognormal_p),
        "powerlaw_vs_truncated_r": float(truncated_r),
        "powerlaw_vs_truncated_p": float(truncated_p),
    }
