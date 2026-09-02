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


def test_public_manifest_checksums_every_published_payload() -> None:
    manifest = load("manifest.json")

    assert "typed-edge-samples.json" not in manifest["files"]
    for name, metadata in manifest["files"].items():
        path = SITE_DATA / name
        assert path.stat().st_size == metadata["bytes"]
        assert sha256(path) == metadata["sha256"]
