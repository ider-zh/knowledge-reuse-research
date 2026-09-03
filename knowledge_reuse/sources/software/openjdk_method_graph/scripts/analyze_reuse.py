#!/usr/bin/env python3
"""Compute direct and cycle-bounded path indegree for an OpenJDK method graph."""

from __future__ import annotations

import argparse
import heapq
import json
from pathlib import Path

import polars as pl

from knowledge_reuse.analysis.path_indegree import weighted_incoming_path_counts
from knowledge_reuse.analysis.rank_shape import compare_rank_reference_curves


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", type=Path, required=True)
    parser.add_argument("--links", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site-json", type=Path)
    return parser.parse_args()


def _subtract_decimal(left: str, right: int) -> str:
    return str(int(left) - right)


def _top_rows(metrics: pl.DataFrame, limit: int = 100) -> list[dict]:
    rows = heapq.nlargest(
        limit,
        metrics.iter_rows(named=True),
        key=lambda row: (int(row["in_paths_source"]), -int(row["node_id"])),
    )
    return [
        {
            "rank": rank,
            "node_id": str(row["node_id"]),
            "label": row["label"],
            "module": row["domain"],
            "direct_unique_callers": row["direct_unique_callers"],
            "direct_call_occurrences": row["direct_call_occurrences"],
            "indirect_incoming_paths": row["indirect_incoming_paths"],
            "all_incoming_paths": row["in_paths_source"],
            "all_incoming_paths_log10": row["in_paths_source_log10"],
            "is_cycle_boundary": row["is_path_cycle_boundary"],
        }
        for rank, row in enumerate(rows, 1)
    ]


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    nodes = pl.read_parquet(args.nodes)
    links = pl.read_parquet(args.links)
    if nodes["graph_id"].n_unique() != 1 or links["graph_id"].n_unique() != 1:
        raise ValueError("analysis requires exactly one graph_id")
    graph_id = nodes["graph_id"][0]
    if graph_id != links["graph_id"][0]:
        raise ValueError("node and link graph_id values differ")

    path_metrics = weighted_incoming_path_counts(nodes["node_id"], links)
    direct = links.group_by("dst_id").agg(
        pl.len().alias("direct_unique_callers"),
        pl.col("multiplicity").sum().alias("direct_call_occurrences"),
    )
    metrics = (
        nodes.join(path_metrics, on="node_id", how="left", validate="1:1")
        .join(direct, left_on="node_id", right_on="dst_id", how="left", validate="1:1")
        .with_columns(
            pl.col("direct_unique_callers").fill_null(0).cast(pl.UInt64),
            pl.col("direct_call_occurrences").fill_null(0).cast(pl.UInt64),
        )
        .with_columns(
            pl.struct(["in_paths_source", "direct_call_occurrences"])
            .map_elements(
                lambda row: _subtract_decimal(
                    row["in_paths_source"], row["direct_call_occurrences"]
                ),
                return_dtype=pl.String,
            )
            .alias("indirect_incoming_paths")
        )
    )
    metrics.write_parquet(args.output / "node_incoming_paths.parquet", compression="zstd")

    positive = metrics["in_paths_source_log10"].drop_nulls().to_numpy()
    rank_shape = compare_rank_reference_curves(positive)
    top_rows = _top_rows(metrics)
    maximum = top_rows[0]
    payload = {
        "schema_version": "1.0",
        "snapshot_id": "openjdk-jdk-28+13",
        "graph_id": graph_id,
        "corpus": {
            "jdk_release": "28-ea+13-812",
            "source_tag": "jdk-28+13",
            "source_commit": "6870f28fe74cbd71419bdd1d1797434366bf8114",
            "node_unit": "JVM method declaration",
            "edge_unit": "resolved bytecode call site",
        },
        "semantics": {
            "direct_unique_callers": "number of distinct caller-to-callee pairs",
            "direct_call_occurrences": "sum of call-site multiplicity on incoming pairs",
            "indirect_incoming_paths": (
                "all non-empty incoming paths minus direct call-site occurrences"
            ),
            "all_incoming_paths": (
                "multiplicity-weighted direct plus indirect paths; propagation stops "
                "when a cyclic strongly connected component is reached"
            ),
            "cycle_boundary": (
                "all methods in a multi-node strongly connected component, plus "
                "methods with a self-loop"
            ),
        },
        "population": {
            "nodes": metrics.height,
            "links": links.height,
            "call_occurrences": int(links["multiplicity"].sum()),
            "positive_path_nodes": len(positive),
            "zero_path_nodes": metrics.height - len(positive),
            "cycle_boundary_nodes": int(metrics["is_path_cycle_boundary"].sum()),
        },
        "path_counts": {
            "maximum": maximum["all_incoming_paths"],
            "maximum_log10": maximum["all_incoming_paths_log10"],
            "median_positive_log10": float(positive.mean())
            if len(positive) == 1
            else float(pl.Series(positive).median()),
        },
        "rank_shape": rank_shape,
        "top_nodes": top_rows,
        "interpretation": {
            "primary": (
                "The incoming-path rank curve is much steeper than Zipf: the fitted "
                "rank exponent is well above one in both reported ranges."
            ),
            "prime": (
                "The reciprocal nth-prime curve is only a decreasing reference shape. "
                "A modestly lower fixed-shape error does not imply a prime-generating "
                "mechanism or a prime distribution."
            ),
            "scope": (
                "Counts describe paths in the static exact-reference graph, not runtime "
                "dispatch frequency, distinct transitive callers, or execution volume."
            ),
        },
        "references": {
            "zipf": "https://en.wikipedia.org/wiki/Zipf%27s_law",
            "nth_prime": "https://dlmf.nist.gov/27.2",
        },
    }
    summary_path = args.output / "reuse_analysis.json"
    summary_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    if args.site_json:
        args.site_json.parent.mkdir(parents=True, exist_ok=True)
        args.site_json.write_text(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
