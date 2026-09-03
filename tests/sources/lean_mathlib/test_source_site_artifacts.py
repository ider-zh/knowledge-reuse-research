import json

from knowledge_reuse.sources.lean_mathlib.export_site import sha256
from knowledge_reuse.sources.lean_mathlib.layout import ROOT, run_results_root


SITE_DATA = (
    ROOT
    / "apps/research-site/public/datasets/lean_mathlib_v1/mathlib-v4.32.1"
)


def load(name: str):
    return json.loads((SITE_DATA / name).read_text())


def test_public_overview_matches_full_source_graph_summary() -> None:
    overview = load("overview.json")
    source_graph = json.loads(
        (run_results_root("full") / "source-graph-summary.json").read_text()
    )

    assert overview["graph_schema_version"] == "lean-source-graph-v1"
    assert overview["headline_metrics"]["source_pairs"] == source_graph["artifacts"][
        "edges"
    ]["rows"]
    assert overview["headline_metrics"]["source_occurrences"] == source_graph[
        "edge_multiplicity_sum"
    ]
    assert overview["headline_metrics"]["self_loop_pairs"] == source_graph[
        "self_loop_edge_count"
    ]
    assert overview["path_indegree"] == {
        "cycle_boundary_node_count": 2640,
        "maximum_exact": "49771243065343156822021307685733",
        "maximum_log10": 31.696978487633263,
        "metric": "in_paths_source",
        "semantics": (
            "exact multiplicity-weighted direct and indirect incoming path count; "
            "paths stop when they reach a cyclic SCC"
        ),
        "storage": "exact decimal string plus base-10 logarithm",
    }


def test_dfunlike_public_case_distinguishes_graph_and_excluded_location() -> None:
    construction = load("construction-cases.json")
    case = next(item for item in construction["edge_cases"] if item["case_id"] == "edge.dfunlike")

    assert case["aggregate"] == {
        "excluded_private_context_locations": 1,
        "source_modules": 227,
        "target_source_occurrences": 386,
        "target_unique_consumers": 370,
    }
    assert case["edges"][0]["multiplicity"] == 2
    assert len(case["source_locations"]) == 2


def test_public_attribution_boundary_partitions_source_contexts() -> None:
    boundary = load("construction-cases.json")["attribution_boundary"]

    assert boundary["unparented"] == {
        "outside_declaration_range": 107586,
        "overlapping_declaration_ranges": 145,
        "total": 109575,
        "unique_declaration_range": 1844,
        "unique_environment_declaration": 1844,
    }
    assert boundary["parent_not_in_environment"] == {
        "example_context": 2090,
        "metaprogram_or_external_context": 53,
        "private_or_eval_context": 109,
        "total": 2252,
    }
    profile = boundary["outside_declaration_profile"]
    assert profile["population"] == 107586
    assert profile["variable_context_count"] == 80439
    assert sum(profile["categories"].values()) == profile["population"]


def test_public_node_sample_exposes_exact_path_indegree() -> None:
    nodes = load("nodes.json")["rows"]
    dfunlike = next(row for row in nodes if row["name"] == "DFunLike.coe")

    assert dfunlike["in_degree_source"] == 370
    assert dfunlike["in_occurrences_source"] == 386
    assert dfunlike["in_paths_source"] == "19302141636508271"
    assert dfunlike["is_path_cycle_boundary"] is False


def test_path_rank_comparison_reports_fixed_shape_evidence() -> None:
    comparison = load("path-rank-comparison.json")
    full = next(
        item for item in comparison["ranges"] if item["range_id"] == "all_positive"
    )
    top = next(item for item in comparison["ranges"] if item["range_id"] == "top_1pct")

    assert comparison["positive_observation_count"] == 178373
    assert full["observation_count"] == 178373
    assert top["observation_count"] == 1784
    assert full["models"]["zipf"]["free_exponent_beta"] > 10
    assert full["models"]["zipf"]["fixed_r_squared_log10"] < 0.2
    assert (
        full["models"]["reciprocal_prime"]["fixed_rmse_log10"]
        < full["models"]["zipf"]["fixed_rmse_log10"]
    )
    assert comparison["references"]["nth_prime_asymptotic"].endswith("27.2#E4")


def test_public_manifest_checksums_every_published_payload() -> None:
    manifest = load("manifest.json")

    assert "typed-edge-samples.json" not in manifest["files"]
    for name, metadata in manifest["files"].items():
        path = SITE_DATA / name
        assert path.stat().st_size == metadata["bytes"]
        assert sha256(path) == metadata["sha256"]
