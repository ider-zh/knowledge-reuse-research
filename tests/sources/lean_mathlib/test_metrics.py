import numpy as np
import polars as pl

from knowledge_reuse.sources.lean_mathlib.metrics import (
    append_domain_examples,
    build_report_examples,
    fit_regression,
    fit_rank_frequency,
    internal_unique_dependency_pairs,
    with_node_metrics,
)


def _node(node_id: int, name: str, kind: str = "theorem", has_value: bool = True) -> dict:
    return {
        "snapshot_id": "test",
        "node_id": node_id,
        "name": name,
        "module": "Mathlib.Test",
        "source_file": "Mathlib/Test.lean",
        "domain": "Test",
        "kind": kind,
        "is_theorem": kind == "theorem",
        "is_definition": kind == "definition",
        "is_generated": False,
        "is_internal": False,
        "has_value": has_value,
        "source_bytes": 10,
        "source_lines": 1,
        "source_tokens": 3,
        "type_expr_nodes": 5,
        "value_expr_nodes": 8 if has_value else None,
        "type_const_unique": 1,
        "value_const_unique": 1 if has_value else None,
        "in_degree_all": 2,
        "in_degree_type": 1,
        "in_degree_value": 1,
        "out_degree_all": 2,
    }


def test_report_examples_bind_real_type_value_and_null_cases() -> None:
    rows = [
        _node(1, "Set", "definition"),
        _node(2, "CategoryTheory.Category", "inductive", False),
        _node(3, "Semiring.toNonAssocSemiring", "definition"),
        _node(4, "CategoryTheory.Limits.colimitLimitToLimitColimit_surjective"),
        _node(5, "constantCoeff_xInTermsOfW"),
        _node(6, "map_pow"),
        _node(7, "padicValRat.of_nat"),
        _node(8, "padicValNat", "definition"),
        _node(9, "DFunLike.coe", "definition"),
    ]
    nodes = pl.DataFrame(rows)
    edges = pl.DataFrame(
        [
            {
                "snapshot_id": "test",
                "src_id": 5,
                "dst_id": 6,
                "edge_type": "VALUE",
                "multiplicity": 2,
            },
            {
                "snapshot_id": "test",
                "src_id": 7,
                "dst_id": 8,
                "edge_type": "TYPE",
                "multiplicity": 1,
            },
            {
                "snapshot_id": "test",
                "src_id": 5,
                "dst_id": 9,
                "edge_type": "TYPE",
                "multiplicity": 3,
            },
            {
                "snapshot_id": "test",
                "src_id": 7,
                "dst_id": 9,
                "edge_type": "VALUE",
                "multiplicity": 1,
            },
        ]
    )

    examples = build_report_examples(nodes, edges, nodes, "test")
    by_id = {row["example_id"]: row for row in examples}

    assert by_id["edge.value.theorem_to_theorem"]["edge_type"] == "VALUE"
    assert by_id["edge.type.theorem_to_definition"]["edge_type"] == "TYPE"
    assert by_id["node.no_value"]["value_expr_nodes"] is None
    assert by_id["node.no_value"]["source_locator"].endswith("::CategoryTheory.Category")
    assert sum(row["concept"] == "reuse indegree" for row in examples) == 2


def test_rank_frequency_fit_recovers_zipf_slope() -> None:
    ranks = np.arange(1, 2_001, dtype=float)
    counts = 10_000 / ranks

    result = fit_rank_frequency(counts, "fixture", xmin=float(counts.min()))

    assert result["status"] == "ok"
    assert abs(result["beta_rank"] - 1.0) < 1e-10
    assert result["r_squared"] > 0.999999
    assert result["tail_n"] == 2_000


def test_node_metrics_keep_unique_consumers_and_occurrence_weight_separate() -> None:
    nodes = pl.DataFrame([_node(1, "A"), _node(2, "B"), _node(3, "C")]).drop(
        "in_degree_all", "in_degree_type", "in_degree_value", "out_degree_all"
    )
    edges = pl.DataFrame(
        {
            "src_id": [1, 1, 3],
            "dst_id": [2, 2, 2],
            "edge_type": ["TYPE", "VALUE", "VALUE"],
            "multiplicity": [2, 5, 7],
        }
    )

    observed = with_node_metrics(nodes, edges).filter(pl.col("node_id") == 2).row(0, named=True)

    assert observed["in_degree_all"] == 2
    assert observed["in_degree_type"] == 1
    assert observed["in_degree_value"] == 2
    assert observed["in_occurrences_all"] == 14
    assert observed["in_occurrences_type"] == 2
    assert observed["in_occurrences_value"] == 12


def test_internal_dependency_pairs_collapse_type_value_duplicates() -> None:
    nodes = pl.DataFrame(
        {
            "node_id": [1, 2, 3],
            "domain": ["Algebra", "Topology", "Topology"],
        }
    )
    edges = pl.DataFrame(
        {
            "src_id": [1, 1, 1],
            "dst_id": [2, 2, 3],
            "edge_type": ["TYPE", "VALUE", "TYPE"],
        }
    )

    pairs = internal_unique_dependency_pairs(nodes, edges)

    assert pairs.height == 2
    assert pairs.select("src_domain").unique().item() == "Algebra"
    assert pairs.select("dst_domain").unique().item() == "Topology"


def test_domain_examples_use_sorted_unique_pairs() -> None:
    nodes = pl.DataFrame(
        [
            _node(1, "A", "definition"),
            {**_node(2, "B", "definition"), "domain": "Other"},
            {**_node(3, "C", "definition"), "domain": "Other"},
        ]
    )
    edges = pl.DataFrame(
        {
            "src_id": [1, 1, 1, 1],
            "dst_id": [3, 2, 2, 1],
            "edge_type": ["VALUE", "VALUE", "TYPE", "TYPE"],
        }
    )
    pairs = internal_unique_dependency_pairs(nodes, edges)
    examples: list[dict] = []

    append_domain_examples(examples, pairs, edges, nodes, "test")

    assert [(row["src_id"], row["dst_id"]) for row in examples] == [
        (1, 2),
        (1, 3),
        (1, 1),
    ]
    assert examples[0]["edge_type"] == "TYPE+VALUE"
    assert "仍只增加 1" in examples[0]["explanation"]


def test_memory_efficient_negative_binomial_uses_all_rows() -> None:
    length = np.arange(1, 401)
    frame = pl.DataFrame(
        {
            "source_tokens": length,
            "in_degree_all": np.maximum(1, (800 / np.sqrt(length)).astype(int)),
            "kind": ["definition"] * len(length),
            "domain": ["Test"] * len(length),
        }
    )

    result = fit_regression(frame, "source_tokens")

    assert result["status"] == "ok_nb2_fixed_dispersion"
    assert result["n"] == len(length)
    assert result["coefficient"] < 0
    assert result["ci_high"] < 0
    assert result["standard_error_type"] == "HC1_sandwich"
    assert result["model_std_error"] > 0
    assert result["pearson_dispersion"] > 0
    assert result["effect_reference_value"] == 200.5
    assert result["doubling_effect_pct_at_reference"] < 0
