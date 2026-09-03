import polars as pl
import pytest

from knowledge_reuse.sources.software.openjdk_method_graph.scripts.analyze_cross_version import (
    _pct,
)
from knowledge_reuse.sources.software.openjdk_method_graph.scripts.analyze_reuse_theorems import (
    _component_size_analysis,
    _fold_for,
)


def test_component_savings_clips_unsigned_bytecode_subtraction() -> None:
    methods = pl.DataFrame(
        {
            "method_id": [1, 2],
            "method_key": ["m/C#a()V", "m/C#b()V"],
            "module_name": ["m", "m"],
            "class_name": ["C", "C"],
            "bytecode_length": pl.Series([1, 10], dtype=pl.UInt32),
            "instruction_count": pl.Series([1, 4], dtype=pl.UInt32),
            "has_code": [True, True],
            "is_synthetic": [False, False],
        }
    )
    calls = pl.DataFrame(
        {
            "callee_method_id": [1, 1, 2],
            "invoke_kind": ["SPECIAL", "SPECIAL", "STATIC"],
            "resolution": ["EXACT", "EXACT", "EXACT"],
        }
    )

    result = _component_size_analysis(methods, calls)

    assert result["display_points"][0]["gross_savings_bytes_per_use"] == 0
    assert result["display_points"][1]["gross_savings_bytes_per_use"] == 7


def test_package_fold_and_growth_percentage_are_deterministic() -> None:
    assert _fold_for("java.lang", 5) == _fold_for("java.lang", 5)
    assert 0 <= _fold_for("java.lang", 5) < 5
    assert _pct(110, 100) == pytest.approx(10.0)
