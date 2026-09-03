import polars as pl

from knowledge_reuse.sources.lean_mathlib.source_graph_metrics import (
    internal_domain_pairs,
    with_source_node_metrics,
)


def test_source_node_metrics_separate_direct_breadth_from_occurrences() -> None:
    nodes = pl.DataFrame(
        {
            "node_id": [1, 2, 3],
            "domain": ["A", "A", "B"],
        }
    )
    edges = pl.DataFrame(
        {
            "src_id": [1, 2, 3, 2],
            "dst_id": [3, 3, 3, 1],
            "multiplicity": [4, 2, 9, 1],
        }
    )

    metrics = with_source_node_metrics(nodes, edges)
    target = metrics.filter(pl.col("node_id") == 3).row(0, named=True)

    assert target["in_degree_source"] == 2
    assert target["in_occurrences_source"] == 6
    assert target["out_degree_source"] == 0
    assert target["in_paths_source"] == "19"
    assert target["is_path_cycle_boundary"] is True


def test_internal_domain_pairs_exclude_self_loops_and_external_targets() -> None:
    nodes = pl.DataFrame({"node_id": [1, 2], "domain": ["A", "B"]})
    edges = pl.DataFrame(
        {
            "src_id": [1, 1, 2],
            "dst_id": [1, 2, 9],
            "multiplicity": [3, 4, 5],
        }
    )

    pairs = internal_domain_pairs(nodes, edges)

    assert pairs.select("src_id", "dst_id", "multiplicity").to_dicts() == [
        {"src_id": 1, "dst_id": 2, "multiplicity": 4}
    ]
    assert pairs.item(0, "src_domain") == "A"
    assert pairs.item(0, "dst_domain") == "B"
