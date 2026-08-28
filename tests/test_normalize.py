import polars as pl

from knowledge_reuse.sources.lean_mathlib.normalize import null_statistics
from scripts.verify_run import SemanticAccumulator, semantic_accumulator


def test_null_statistics_counts_missing_values() -> None:
    frame = pl.DataFrame({"a": [1, None], "b": [None, None]})
    assert null_statistics(frame) == {"a": 1, "b": 2}


def test_semantic_accumulator_is_merge_order_independent() -> None:
    left = semantic_accumulator([{"record": "edge", "src": "a", "dst": "b"}])
    right = semantic_accumulator([{"record": "edge", "src": "c", "dst": "d"}])
    assert left.merge(right).digest() == right.merge(left).digest()
    assert left.merge(SemanticAccumulator()).digest() == left.digest()
