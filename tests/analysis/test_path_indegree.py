import math

import polars as pl

from knowledge_reuse.analysis.path_indegree import weighted_incoming_path_counts


def calculate(edges: list[tuple[int, int, int]]) -> dict[int, dict[str, object]]:
    result = weighted_incoming_path_counts(
        pl.Series("node_id", [0, 1, 2, 3], dtype=pl.UInt64),
        pl.DataFrame(
            edges,
            schema=["src_id", "dst_id", "multiplicity"],
            orient="row",
        ).cast({"src_id": pl.UInt64, "dst_id": pl.UInt64, "multiplicity": pl.UInt64}),
    )
    return {row["node_id"]: row for row in result.iter_rows(named=True)}


def test_chain_counts_direct_and_indirect_paths() -> None:
    rows = calculate([(0, 1, 1), (1, 2, 1)])

    assert rows[0]["in_paths_source"] == "0"
    assert rows[1]["in_paths_source"] == "1"
    assert rows[2]["in_paths_source"] == "2"


def test_diamond_preserves_two_indirect_routes() -> None:
    rows = calculate([(0, 1, 1), (0, 2, 1), (1, 3, 1), (2, 3, 1)])

    assert rows[3]["in_paths_source"] == "4"


def test_edge_multiplicity_multiplies_path_choices() -> None:
    rows = calculate([(0, 1, 2), (1, 2, 3)])

    assert rows[1]["in_paths_source"] == "2"
    assert rows[2]["in_paths_source"] == "9"
    assert math.isclose(rows[2]["in_paths_source_log10"], math.log10(9))


def test_cycle_nodes_are_terminal_for_indirect_propagation() -> None:
    rows = calculate([(0, 1, 1), (1, 2, 1), (2, 1, 1), (2, 3, 3)])

    assert rows[1]["in_paths_source"] == "2"
    assert rows[2]["in_paths_source"] == "1"
    assert rows[3]["in_paths_source"] == "3"
    assert rows[1]["is_path_cycle_boundary"] is True
    assert rows[2]["is_path_cycle_boundary"] is True


def test_self_loop_is_direct_but_does_not_seed_longer_paths() -> None:
    rows = calculate([(0, 1, 1), (1, 1, 2), (1, 2, 3), (2, 3, 1)])

    assert rows[1]["in_paths_source"] == "3"
    assert rows[2]["in_paths_source"] == "3"
    assert rows[3]["in_paths_source"] == "1"
    assert rows[1]["is_path_cycle_boundary"] is True
