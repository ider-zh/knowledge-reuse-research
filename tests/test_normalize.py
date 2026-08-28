import polars as pl

from knowledge_reuse.sources.lean_mathlib.normalize import null_statistics, sanitize_expr_counts
from scripts.verify_run import SemanticAccumulator, canonical_semantic_digest, semantic_accumulator


def test_null_statistics_counts_missing_values() -> None:
    frame = pl.DataFrame({"a": [1, None], "b": [None, None]})
    assert null_statistics(frame) == {"a": 1, "b": 2}


def test_saturated_expr_counts_are_explicitly_excluded() -> None:
    frame = pl.DataFrame(
        {
            "type_expr_nodes": [12, 2**64 - 1, 7],
            "type_expr_nodes_saturated": [False, True, None],
            "value_expr_nodes": [None, 2**64 - 1, 9],
            "value_expr_nodes_saturated": [None, True, False],
        }
    )
    normalized = sanitize_expr_counts(frame.lazy()).collect()
    assert normalized["type_expr_nodes"].to_list() == [12, None, 7]
    assert normalized["value_expr_nodes"].to_list() == [None, None, 9]
    assert normalized["type_expr_nodes_saturated"].to_list() == [False, True, False]


def test_semantic_digest_adapts_pre_saturation_nodes() -> None:
    legacy = [{"record": "node", "name": "n", "has_value": True}]
    current = [
        {
            "record": "node",
            "name": "n",
            "has_value": True,
            "type_expr_nodes_saturated": False,
            "value_expr_nodes_saturated": False,
        }
    ]
    assert canonical_semantic_digest(legacy) == canonical_semantic_digest(current)


def test_semantic_accumulator_is_merge_order_independent() -> None:
    left = semantic_accumulator([{"record": "edge", "src": "a", "dst": "b"}])
    right = semantic_accumulator([{"record": "edge", "src": "c", "dst": "d"}])
    assert left.merge(right).digest() == right.merge(left).digest()
    assert left.merge(SemanticAccumulator()).digest() == left.digest()
