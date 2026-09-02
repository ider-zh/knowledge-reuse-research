import polars as pl
import pytest

from knowledge_reuse.sources.lean_mathlib.commands.verify_run import (
    SemanticAccumulator,
    semantic_accumulator,
)
from knowledge_reuse.sources.lean_mathlib.normalize import (
    null_statistics,
    validate_weighted_edges,
)
from knowledge_reuse.sources.lean_mathlib.normalize_complexity import (
    select_graph_complexity,
)


def test_null_statistics_counts_missing_values() -> None:
    frame = pl.DataFrame({"a": [1, None], "b": [None, None]})
    assert null_statistics(frame) == {"a": 1, "b": 2}


def weighted_edges(multiplicities: list[int | None]) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "snapshot_id": ["s"] * len(multiplicities),
            "src": ["a"] * len(multiplicities),
            "dst": ["b"] * len(multiplicities),
            "edge_type": ["VALUE"] * len(multiplicities),
            "multiplicity": multiplicities,
        },
        schema_overrides={"multiplicity": pl.UInt64},
    )


def test_weighted_edges_accept_positive_multiplicity() -> None:
    validate_weighted_edges(weighted_edges([3]))


@pytest.mark.parametrize(
    ("multiplicities", "message"),
    [([2, 3], "duplicate typed-edge keys"), ([None], "non-null"), ([0], "positive")],
)
def test_weighted_edges_reject_lossy_or_invalid_encoding(
    multiplicities: list[int | None], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_weighted_edges(weighted_edges(multiplicities))


def test_semantic_accumulator_is_merge_order_independent() -> None:
    left = semantic_accumulator([{"record": "edge", "src": "a", "dst": "b"}])
    right = semantic_accumulator([{"record": "edge", "src": "c", "dst": "d"}])
    assert left.merge(right).digest() == right.merge(left).digest()
    assert left.merge(SemanticAccumulator()).digest() == left.digest()


def test_complexity_aliases_follow_graph_provenance_when_metrics_agree() -> None:
    raw = pl.DataFrame(
        {
            "snapshot_id": ["s", "s", "s"],
            "name": ["generated", "generated", "ordinary"],
            "module": ["M1", "M2", "M2"],
            "has_value": [True, True, False],
            "type_expr_unique_ptr_nodes": [7, 7, 2],
        }
    )
    graph = pl.DataFrame(
        {"name": ["generated", "ordinary"], "module": ["M2", "M2"]}
    )
    selected, alias_rows = select_graph_complexity(raw, graph)
    assert alias_rows == 1
    assert selected.filter(pl.col("name") == "generated")["module"][0] == "M2"


def test_complexity_aliases_reject_metric_disagreement() -> None:
    raw = pl.DataFrame(
        {
            "snapshot_id": ["s", "s"],
            "name": ["generated", "generated"],
            "module": ["M1", "M2"],
            "has_value": [True, True],
            "type_expr_unique_ptr_nodes": [7, 8],
        }
    )
    graph = pl.DataFrame({"name": ["generated"], "module": ["M2"]})
    with pytest.raises(ValueError, match="disagree"):
        select_graph_complexity(raw, graph)
