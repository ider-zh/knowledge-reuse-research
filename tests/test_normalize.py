import polars as pl

from knowledge_reuse.sources.lean_mathlib.normalize import null_statistics, sanitize_expr_counts


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
