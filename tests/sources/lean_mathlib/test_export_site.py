import json

import polars as pl

from knowledge_reuse.sources.lean_mathlib.export_site import (
    attribution_boundary,
    domain_edge_sample,
    external_target_sample,
    public_node_sample,
    rank_frequency_distribution,
    source_edge_sample,
)


def test_attribution_boundary_distinguishes_declarations_from_source_contexts(
    tmp_path,
) -> None:
    module_path = tmp_path / "Mathlib" / "Fixture.ilean"
    module_path.parent.mkdir(parents=True)
    module_path.write_text(
        json.dumps(
            {
                "decls": {
                    "Fixture.outer": [10, 0, 20, 0, 10, 8, 10, 13],
                    "Fixture.inner": [14, 0, 16, 0, 14, 8, 14, 13],
                }
            }
        )
    )
    source_path = tmp_path / "Mathlib" / "Fixture.lean"
    source_lines = [""] * 21
    source_lines[5] = "variable [FixtureClass α]"
    source_path.write_text("\n".join(source_lines))
    unparented = pl.DataFrame(
        {
            "module": ["Mathlib.Fixture", "Mathlib.Fixture", "Mathlib.Fixture"],
            "start_line": [5, 11, 15],
            "start_character": [0, 2, 2],
            "end_line": [5, 11, 15],
            "end_character": [3, 5, 5],
        }
    )
    unresolved = pl.DataFrame(
        {
            "parent_decl": [
                "Fixture._example",
                "_private.Fixture.0._example",
                "_private.Fixture.0._eval",
                "One",
            ]
        }
    )

    result = attribution_boundary(
        unparented,
        unresolved,
        {"Fixture.outer", "Fixture.inner"},
        tmp_path,
        tmp_path,
    )

    assert result["unparented"] == {
        "total": 3,
        "outside_declaration_range": 1,
        "unique_declaration_range": 1,
        "unique_environment_declaration": 1,
        "overlapping_declaration_ranges": 1,
    }
    assert result["outside_declaration_profile"]["variable_context_count"] == 1
    assert result["outside_declaration_profile"]["variable_context_share"] == 1.0
    assert result["parent_not_in_environment"] == {
        "total": 4,
        "example_context": 2,
        "private_or_eval_context": 1,
        "metaprogram_or_external_context": 1,
    }


def test_rank_frequency_display_uses_complete_sorted_population_and_zipf_reference() -> None:
    nodes = pl.DataFrame(
        {
            "kind": ["theorem", "theorem", "definition", "definition", "definition"],
            "in_degree_source": [100, 10, 50, 5, 0],
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
    payload = rank_frequency_distribution(nodes, fits, "snapshot")
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
            "in_degree_source": [20, 1],
            "in_occurrences_source": [25, 1],
            "in_paths_source": ["125", "1"],
            "in_paths_source_log10": [2.09691, 0.0],
            "is_path_cycle_boundary": [False, False],
            "out_degree_source": [2, 3],
            "out_occurrences_source": [4, 3],
        }
    )
    sample = public_node_sample(nodes)
    assert sample.height == 2
    reasons = sample.filter(pl.col("name") == "A")["sample_reason"].item()
    assert "SOURCE 复用入度前 120" in reasons
    assert "Value Expr 展开复杂度前 60" in reasons


def test_external_target_sample_counts_consumers_and_source_occurrences() -> None:
    edges = pl.DataFrame(
        {
            "src_id": [1, 1, 2, 2],
            "dst_id": [9, 9, 9, 3],
            "edge_type": ["SOURCE", "SOURCE", "SOURCE", "SOURCE"],
            "multiplicity": [2, 3, 1, 1],
        }
    )
    external = pl.DataFrame(
        {
            "node_id": [9],
            "name": ["External.X"],
            "target_module_hints": [["Lean"]],
            "target_module_hint_count": [1],
        }
    )
    row = external_target_sample(edges, external).row(0, named=True)
    assert row["unique_consumer_count"] == 2
    assert row["source_pair_count"] == 3
    assert row["source_occurrence_count"] == 6


def test_domain_edge_sample_keeps_source_multiplicity_and_cross_edges() -> None:
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
            "src_id": [1, 1, 3],
            "dst_id": [2, 3, 2],
            "edge_type": ["SOURCE", "SOURCE", "SOURCE"],
            "multiplicity": [4, 1, 2],
        }
    )
    external = pl.DataFrame(
        schema={"node_id": pl.Int64, "name": pl.String}
    )
    sample = domain_edge_sample(edges, nodes, external, per_cell=3)
    cross = sample.filter((pl.col("src_id") == 1) & (pl.col("dst_id") == 2)).row(0, named=True)
    assert cross["edge_type"] == "SOURCE"
    assert cross["multiplicity"] == 4
    assert cross["src_domain"] == "Algebra"
    assert cross["dst_domain"] == "Topology"
    assert cross["is_cross_domain"] is True
    assert sample.filter(pl.col("src_domain") == pl.col("dst_domain")).height == 1


def test_source_edge_sample_keeps_multiplicity_self_loop_and_external_group() -> None:
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
            "src_id": [1, 1, 2],
            "dst_id": [2, 9, 2],
            "edge_type": ["SOURCE", "SOURCE", "SOURCE"],
            "multiplicity": [4, 2, 3],
        }
    )
    sample = source_edge_sample(edges, nodes, external)
    assert set(sample["edge_type"].to_list()) == {"SOURCE"}
    external_row = sample.filter(pl.col("dst_id") == 9).row(0, named=True)
    assert external_row["dst_domain"] == "EXTERNAL"
    assert external_row["is_external_target"] is True
    assert external_row["multiplicity"] == 2
    self_loop = sample.filter(pl.col("src_id") == pl.col("dst_id")).row(0, named=True)
    assert self_loop["is_self_loop"] is True
