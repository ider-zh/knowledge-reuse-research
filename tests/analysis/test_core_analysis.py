import numpy as np
import pytest

from knowledge_reuse.analysis.concentration import gini, hhi, top_share


def test_concentration_metrics_are_source_neutral() -> None:
    values = np.array([0, 0, 1, 3], dtype=float)
    assert gini(values) == pytest.approx(0.625)
    assert hhi(values) == pytest.approx(0.625)
    assert top_share(values, 0.25) == pytest.approx(0.75)


def test_top_share_rejects_invalid_fraction() -> None:
    with pytest.raises(ValueError):
        top_share(np.array([1]), 0)
