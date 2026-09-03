import math

import numpy as np

from knowledge_reuse.analysis.rank_shape import compare_rank_reference_curves, first_n_primes


def test_first_n_primes_returns_exact_sequence() -> None:
    assert first_n_primes(8).tolist() == [2, 3, 5, 7, 11, 13, 17, 19]


def test_exact_zipf_curve_is_identified_by_fixed_and_free_fits() -> None:
    ranks = np.arange(1, 1001, dtype=float)
    values = 8.0 - np.log10(ranks)

    result = compare_rank_reference_curves(values)
    full = next(item for item in result["ranges"] if item["range_id"] == "all_positive")
    zipf = full["models"]["zipf"]

    assert math.isclose(zipf["fixed_rmse_log10"], 0.0, abs_tol=1e-12)
    assert math.isclose(zipf["fixed_r_squared_log10"], 1.0, abs_tol=1e-12)
    assert math.isclose(zipf["free_exponent_beta"], 1.0, abs_tol=1e-12)


def test_exact_reciprocal_prime_curve_prefers_prime_template() -> None:
    primes = first_n_primes(1000).astype(float)
    values = 8.0 - np.log10(primes)

    result = compare_rank_reference_curves(values)
    full = next(item for item in result["ranges"] if item["range_id"] == "all_positive")

    assert full["models"]["reciprocal_prime"]["fixed_rmse_log10"] < 1e-12
    assert (
        full["models"]["reciprocal_prime"]["fixed_rmse_log10"]
        < full["models"]["zipf"]["fixed_rmse_log10"]
    )
