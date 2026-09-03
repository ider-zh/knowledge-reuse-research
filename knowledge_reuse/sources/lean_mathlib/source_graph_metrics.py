"""Derive research metrics from the `.ilean` source-reference graph."""

from __future__ import annotations

import argparse
import json
import math
import tomllib
from typing import Any

import numpy as np
import polars as pl

from knowledge_reuse.analysis.concentration import gini, top_share
from knowledge_reuse.analysis.path_indegree import weighted_incoming_path_counts
from knowledge_reuse.analysis.powerlaw import fit_tail
from knowledge_reuse.analysis.rank_shape import compare_rank_reference_curves
from knowledge_reuse.sources.lean_mathlib.layout import (
    CONFIG_PATH,
    run_results_root,
    source_graph_normalized_root,
)
from knowledge_reuse.sources.lean_mathlib.metrics import fit_rank_frequency


CONFIG = tomllib.loads(CONFIG_PATH.read_text())


def metrics_root(run_kind: str):
    return run_results_root(run_kind) / "source_graph_metrics"


def with_source_node_metrics(nodes: pl.DataFrame, edges: pl.DataFrame) -> pl.DataFrame:
    """Attach direct SOURCE metrics and exact cycle-bounded incoming paths."""

    internal_ids = nodes.select("node_id")
    internal_edges = (
        edges.join(
            internal_ids.rename({"node_id": "src_id"}), on="src_id", how="inner"
        )
        .join(
            internal_ids.rename({"node_id": "dst_id"}), on="dst_id", how="inner"
        )
    )
    reuse_edges = internal_edges.filter(pl.col("src_id") != pl.col("dst_id"))
    incoming = reuse_edges.group_by("dst_id").agg(
        pl.col("src_id").n_unique().alias("in_degree_source"),
        pl.col("multiplicity").sum().alias("in_occurrences_source"),
    )
    outgoing = edges.filter(pl.col("src_id") != pl.col("dst_id")).group_by("src_id").agg(
        pl.col("dst_id").n_unique().alias("out_degree_source"),
        pl.col("multiplicity").sum().alias("out_occurrences_source"),
    )
    path_counts = weighted_incoming_path_counts(
        nodes["node_id"], internal_edges.select("src_id", "dst_id", "multiplicity")
    )
    return (
        nodes.join(incoming, left_on="node_id", right_on="dst_id", how="left")
        .join(outgoing, left_on="node_id", right_on="src_id", how="left")
        .join(path_counts, on="node_id", how="left", validate="1:1")
        .with_columns(
            pl.col(column).fill_null(0).cast(pl.UInt64)
            for column in (
                "in_degree_source",
                "in_occurrences_source",
                "out_degree_source",
                "out_occurrences_source",
            )
        )
    )


def internal_domain_pairs(nodes: pl.DataFrame, edges: pl.DataFrame) -> pl.DataFrame:
    identities = nodes.select("node_id", "domain")
    return (
        edges.filter(pl.col("src_id") != pl.col("dst_id"))
        .join(
            identities.rename({"node_id": "src_id", "domain": "src_domain"}),
            on="src_id",
            how="inner",
        )
        .join(
            identities.rename({"node_id": "dst_id", "domain": "dst_domain"}),
            on="dst_id",
            how="inner",
        )
    )


def rank_populations(node_metrics: pl.DataFrame) -> dict[str, np.ndarray]:
    return {
        "all_declarations": node_metrics["in_degree_source"].to_numpy(),
        "kind:theorem": node_metrics.filter(pl.col("kind") == "theorem")[
            "in_degree_source"
        ].to_numpy(),
        "kind:definition": node_metrics.filter(pl.col("kind") == "definition")[
            "in_degree_source"
        ].to_numpy(),
    }


def domain_outputs(
    nodes: pl.DataFrame, node_metrics: pl.DataFrame, pairs: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame]:
    matrix = (
        pairs.group_by("src_domain", "dst_domain")
        .agg(
            pl.len().alias("dependency_pair_count"),
            pl.col("multiplicity").sum().alias("source_occurrence_count"),
        )
        .with_columns(
            (
                pl.col("dependency_pair_count")
                / pl.col("dependency_pair_count").sum().over("src_domain")
            ).alias("row_share")
        )
        .sort("src_domain", "dst_domain")
    )
    target_domain_count = pairs["dst_domain"].n_unique()
    rows: list[dict[str, Any]] = []
    for domain in sorted(nodes["domain"].unique().drop_nulls().to_list()):
        domain_nodes = node_metrics.filter(pl.col("domain") == domain)
        outbound = matrix.filter(pl.col("src_domain") == domain)
        probabilities = outbound["row_share"].to_numpy()
        entropy = (
            float(-(probabilities * np.log(probabilities)).sum()) if probabilities.size else 0.0
        )
        target_counts = (
            pairs.filter(pl.col("src_domain") == domain)
            .group_by("dst_id")
            .agg(pl.col("src_id").n_unique().alias("degree"))
        )
        values = target_counts["degree"].to_numpy()
        internal_count = outbound.filter(pl.col("src_domain") == pl.col("dst_domain"))[
            "dependency_pair_count"
        ].sum()
        total = outbound["dependency_pair_count"].sum()
        rows.append(
            {
                "domain": domain,
                "node_count": domain_nodes.height,
                "reused_target_count": target_counts.height,
                "edge_count": int(total or 0),
                "gini": gini(values),
                "top_1pct_share": top_share(values, 0.01),
                "top_5pct_share": top_share(values, 0.05),
                "top_10pct_share": top_share(values, 0.10),
                "internal_dependency_share": (
                    float(internal_count / total) if total else 0.0
                ),
                "outbound_domain_diversity": outbound["dst_domain"].n_unique(),
                "reference_entropy_proxy": (
                    entropy / math.log(target_domain_count) if target_domain_count > 1 else 0.0
                ),
                "effective_target_domains": math.exp(entropy),
                "rank_exponent_beta": None,
            }
        )
    return matrix, pl.DataFrame(rows)


def analyze_source_graph(run_kind: str = "full") -> dict[str, Any]:
    snapshot = CONFIG["snapshot_id"]
    graph_root = source_graph_normalized_root(snapshot, run_kind)
    output = metrics_root(run_kind)
    output.mkdir(parents=True, exist_ok=True)
    nodes = pl.read_parquet(graph_root / "nodes.parquet")
    edges = pl.read_parquet(graph_root / "edges.parquet")
    external_nodes = pl.read_parquet(graph_root / "external_nodes.parquet")
    source_manifest = json.loads((graph_root / "manifest.json").read_text())

    node_metrics = with_source_node_metrics(nodes, edges)
    pairs = internal_domain_pairs(nodes, edges)
    domain_matrix, domain_metrics = domain_outputs(nodes, node_metrics, pairs)
    populations = rank_populations(node_metrics)
    powerlaw_rows = [fit_tail(values, name) for name, values in populations.items()]
    powerlaw_by_name = {row["population"]: row for row in powerlaw_rows}
    rank_rows = [
        fit_rank_frequency(values, name, powerlaw_by_name[name].get("xmin"))
        for name, values in populations.items()
    ]

    positive = node_metrics.filter(pl.col("in_degree_source") > 0)[
        "in_degree_source"
    ].to_numpy()
    repeated = edges.filter(pl.col("multiplicity") > 1)
    non_self = edges.filter(pl.col("src_id") != pl.col("dst_id"))
    ranked_paths = node_metrics.filter(
        pl.col("in_paths_source_log10").is_not_null()
    ).sort("in_paths_source_log10", descending=True)
    path_rank_comparison = compare_rank_reference_curves(
        node_metrics["in_paths_source_log10"].drop_nulls().to_numpy()
    )
    summary = {
        "schema_version": "lean-source-graph-analysis-v2",
        "graph_schema_version": "lean-source-graph-v1",
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "internal_declaration_count": nodes.height,
        "external_target_count": external_nodes.height,
        "source_pair_count": edges.height,
        "source_occurrence_count": int(edges["multiplicity"].sum()),
        "non_self_pair_count": non_self.height,
        "non_self_occurrence_count": int(non_self["multiplicity"].sum()),
        "repeated_pair_count": repeated.height,
        "self_loop_pair_count": int(source_manifest["self_loop_edge_count"]),
        "self_loop_occurrence_count": int(source_manifest["self_loop_multiplicity"]),
        "unparented_usage_count": int(source_manifest["unparented_usage_count"]),
        "unresolved_parent_usage_count": int(
            source_manifest["unresolved_parent_usage_count"]
        ),
        "path_indegree": {
            "metric": "in_paths_source",
            "semantics": (
                "exact multiplicity-weighted direct and indirect incoming path count; "
                "paths stop when they reach a cyclic SCC"
            ),
            "storage": "exact decimal string plus base-10 logarithm",
            "cycle_boundary_node_count": int(
                node_metrics["is_path_cycle_boundary"].sum()
            ),
            "maximum_exact": (
                ranked_paths.item(0, "in_paths_source") if ranked_paths.height else "0"
            ),
            "maximum_log10": (
                float(ranked_paths.item(0, "in_paths_source_log10"))
                if ranked_paths.height
                else None
            ),
        },
        "positive_reused_target_count": int(positive.size),
        "reuse_concentration": {
            "population": "positive direct non-self SOURCE indegree targets",
            "gini": gini(positive),
            "top_1pct_share": top_share(positive, 0.01),
            "top_5pct_share": top_share(positive, 0.05),
            "top_10pct_share": top_share(positive, 0.10),
        },
    }
    node_metrics.write_parquet(output / "node_metrics.parquet", compression="zstd")
    domain_matrix.write_parquet(output / "domain_matrix.parquet", compression="zstd")
    domain_metrics.write_parquet(output / "domain_metrics.parquet", compression="zstd")
    pl.DataFrame(powerlaw_rows).write_parquet(output / "powerlaw_fits.parquet", compression="zstd")
    pl.DataFrame(rank_rows).write_parquet(
        output / "rank_frequency_fits.parquet", compression="zstd"
    )
    (output / "path_rank_comparison.json").write_text(
        json.dumps(path_rank_comparison, indent=2, sort_keys=True) + "\n"
    )
    (output / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    result = analyze_source_graph("smoke" if args.smoke else "full")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
