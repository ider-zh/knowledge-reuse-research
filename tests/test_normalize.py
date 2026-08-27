import polars as pl

from knowledge_reuse.sources.lean_mathlib.normalize import null_statistics


def test_null_statistics_counts_missing_values() -> None:
    frame = pl.DataFrame({"a": [1, None], "b": [None, None]})
    assert null_statistics(frame) == {"a": 1, "b": 2}
