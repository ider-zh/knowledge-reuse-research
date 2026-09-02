import polars as pl

from knowledge_reuse.sources.lean_mathlib.export_site import (
    domain_edge_sample,
    external_target_sample,
    public_node_sample,
    rank_frequency_distribution,
    typed_edge_sample,
)


def test_rank_frequency_display_uses_complete_sorted_population_and_zipf_reference() -> None:
    nodes = pl.DataFrame(
        {
            "kind": ["theorem", "theorem", "definition", "definition", "definition"],
            "in_degree_all": [100, 10, 50, 5, 0],
        }
    )
    fits = pl.DataFrame(
        {
            "population": ["all_declarations", "kind:theorem", "kind:definition"],
            "status": ["ok", "ok", "ok"],
            "tail_n": [2, 2, 2],
            "xmin": [50.0, 10.0, 5.0],
            "beta_rank": [1.0, 0.9, 1.2],
            "intercept": [0.0, 0.0, 0.0],
            "r_squared": [0.99, 0.98, 0.97],
        }
    )
    payload = rank_frequency_distribution(nodes, fits)
    all_series = payload["series"][0]
    assert all_series["positive_n"] == 4
    assert [point["empirical_degree"] for point in all_series["points"]] == [100, 50, 10, 5]
    assert all_series["points"][0]["zipf_degree"] == 1.0
    assert all_series["points"][2]["zipf_degree"] is None


def test_public_node_sample_explains_overlapping_selection_reasons() -> None:
    nodes = pl.DataFrame(
        {
            "node_id": [1, 2],
            "name": ["A", "B"],
            "module": ["Mathlib.Algebra.A", "Mathlib.Topology.B"],
            "domain": ["Algebra", "Topology"],
            "kind": ["definition", "theorem"],
            "has_value": [True, True],
            "source_tokens": [10, 20],
            "type_expr_unique_ptr_nodes": [3, 4],
            "value_expr_unique_ptr_nodes": [5, 6],
            "value_expr_tree_occurrences": [100, 2],
            "in_degree_all": [20, 1],
            "in_degree_type": [5, 1],
            "in_degree_value": [15, 0],
            "out_degree_all": [2, 3],
        }
    )
    sample = public_node_sample(nodes)
    assert sample.height == 2
    reasons = sample.filter(pl.col("name") == "A")["sample_reason"].item()
    assert "全库复用入度前 120" in reasons
    assert "Value 展开树规模前 60" in reasons


def test_external_target_sample_counts_consumers_and_typed_edges() -> None:
    edges = pl.DataFrame(
        {
            "src_id": [1, 1, 2, 2],
            "dst_id": [9, 9, 9, 3],
            "edge_type": ["TYPE", "VALUE", "VALUE", "TYPE"],
        }
    )
    external = pl.DataFrame({"node_id": [9], "name": ["External.X"]})
    row = external_target_sample(edges, external).row(0, named=True)
    assert row["unique_consumer_count"] == 2
    assert row["typed_edge_count"] == 3
    assert row["type_edge_count"] == 1
    assert row["value_edge_count"] == 2


def test_domain_edge_sample_collapses_type_value_and_keeps_cross_edges() -> None:
    nodes = pl.DataFrame(
        {
            "node_id": [1, 2, 3],
            "name": ["A", "B", "C"],
            "module": ["Mathlib.Algebra.A", "Mathlib.Topology.B", "Mathlib.Topology.C"],
            "domain": ["Algebra", "Topology", "Topology"],
            "kind": ["theorem", "definition", "theorem"],
        }
    )
    edges = pl.DataFrame(
        {
            "src_id": [1, 1, 1, 3],
            "dst_id": [2, 2, 3, 2],
            "edge_type": ["TYPE", "VALUE", "TYPE", "VALUE"],
        }
    )
    sample = domain_edge_sample(edges, nodes, per_cell=3)
    cross = sample.filter((pl.col("src_id") == 1) & (pl.col("dst_id") == 2)).row(0, named=True)
    assert cross["edge_types"] == "TYPE+VALUE"
    assert cross["src_domain"] == "Algebra"
    assert cross["dst_domain"] == "Topology"
    assert cross["is_cross_domain"] is True
    assert sample.filter(pl.col("src_domain") == pl.col("dst_domain")).height == 1


def test_typed_edge_sample_keeps_edge_type_and_external_group() -> None:
    nodes = pl.DataFrame(
        {
            "node_id": [1, 2],
            "name": ["A", "B"],
            "module": ["Mathlib.Algebra.A", "Mathlib.Topology.B"],
            "domain": ["Algebra", "Topology"],
            "kind": ["theorem", "definition"],
        }
    )
    external = pl.DataFrame({"node_id": [9], "name": ["External.X"]})
    edges = pl.DataFrame(
        {
            "src_id": [1, 1, 1],
            "dst_id": [2, 2, 9],
            "edge_type": ["TYPE", "VALUE", "VALUE"],
            "multiplicity": [1, 4, 2],
        }
    )
    sample = typed_edge_sample(edges, nodes, external)
    assert set(sample["edge_type"].to_list()) == {"TYPE", "VALUE"}
    external_row = sample.filter(pl.col("dst_id") == 9).row(0, named=True)
    assert external_row["dst_domain"] == "EXTERNAL"
    assert external_row["is_external_target"] is True
    assert external_row["multiplicity"] == 2
