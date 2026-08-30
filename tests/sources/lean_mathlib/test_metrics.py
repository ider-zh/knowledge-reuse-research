import polars as pl

from knowledge_reuse.sources.lean_mathlib.metrics import build_report_examples


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
            {"snapshot_id": "test", "src_id": 5, "dst_id": 6, "edge_type": "VALUE", "multiplicity": None},
            {"snapshot_id": "test", "src_id": 7, "dst_id": 8, "edge_type": "TYPE", "multiplicity": None},
            {"snapshot_id": "test", "src_id": 5, "dst_id": 9, "edge_type": "TYPE", "multiplicity": None},
            {"snapshot_id": "test", "src_id": 7, "dst_id": 9, "edge_type": "VALUE", "multiplicity": None},
        ]
    )

    examples = build_report_examples(nodes, edges, nodes, "test")
    by_id = {row["example_id"]: row for row in examples}

    assert by_id["edge.value.theorem_to_theorem"]["edge_type"] == "VALUE"
    assert by_id["edge.type.theorem_to_definition"]["edge_type"] == "TYPE"
    assert by_id["node.no_value"]["value_expr_nodes"] is None
    assert sum(row["concept"] == "reuse indegree" for row in examples) == 2
