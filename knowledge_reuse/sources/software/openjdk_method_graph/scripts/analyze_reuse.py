#!/usr/bin/env python3
"""Compute direct and cycle-bounded path indegree for an OpenJDK method graph."""

from __future__ import annotations

import argparse
import heapq
import json
from pathlib import Path
from zipfile import ZipFile

import polars as pl

from knowledge_reuse.analysis.path_indegree import weighted_incoming_path_counts
from knowledge_reuse.analysis.rank_shape import compare_rank_reference_curves


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--nodes", type=Path, required=True)
    parser.add_argument("--links", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site-json", type=Path)
    parser.add_argument("--methods", type=Path)
    parser.add_argument("--method-edges", type=Path)
    parser.add_argument("--call-sites", type=Path)
    parser.add_argument("--source-zip", type=Path)
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


def _metric_sample(row: dict) -> dict:
    return {
        "node_id": str(row["node_id"]),
        "label": row["label"],
        "module": row["domain"],
        "direct_unique_callers": row["direct_unique_callers"],
        "direct_call_occurrences": row["direct_call_occurrences"],
        "indirect_incoming_paths": row["indirect_incoming_paths"],
        "all_incoming_paths": row["in_paths_source"],
        "is_cycle_boundary": row["is_path_cycle_boundary"],
    }


def _paper_reuse_analysis(metrics: pl.DataFrame) -> dict:
    """Reproduce Veldhuizen's reference-count rank method for JVM methods."""

    referenced = metrics.filter(pl.col("direct_call_occurrences") > 0)
    log10_uses = referenced["direct_call_occurrences"].log10().to_numpy()
    rank_shape = compare_rank_reference_curves(log10_uses)
    rank_shape.update(
        {
            "metric": "direct_call_occurrences_log10",
            "comparison_space": "ordinary least squares in log10(reference count) space",
        }
    )
    return {
        "paper": {
            "title": "Software Libraries and Their Reuse: Entropy, Kolmogorov Complexity, and Zipf's Law",
            "section": "Reuse and Zipf's Law / Section 6 experimental data collection",
            "url": "https://arxiv.org/abs/cs/0508023v3",
        },
        "method_alignment": {
            "paper_component": "library subroutine",
            "openjdk_component": "JVM method declaration",
            "paper_use": "static reference to a library subroutine in collected executable/shared objects",
            "openjdk_use": "resolved bytecode invocation call site targeting the method",
            "ranking": "components sorted by descending number of references",
            "plot": "log-log rank n versus number of uses, compared with c*n^-1",
            "rank_offset": (
                "none; unlike the paper's SunOS and Mac OS X series, this corpus does not "
                "omit a higher-frequency component category analogous to machine instructions"
            ),
        },
        "population": {
            "all_methods": metrics.height,
            "referenced_methods": referenced.height,
            "unreferenced_methods": metrics.height - referenced.height,
            "references": int(referenced["direct_call_occurrences"].sum()),
            "singleton_methods": referenced.filter(
                pl.col("direct_call_occurrences") == 1
            ).height,
            "maximum_references": int(referenced["direct_call_occurrences"].max()),
        },
        "rank_shape": rank_shape,
    }


def _source_excerpt(
    source_zip: Path, module: str, class_name: str, source_file: str, start: int, end: int
) -> str:
    package = class_name.rpartition("/")[0]
    member = f"{module}/{package}/{source_file}" if package else f"{module}/{source_file}"
    with ZipFile(source_zip) as archive:
        lines = archive.read(member).decode("utf-8").splitlines()
    return "\n".join(lines[start - 1 : end])


def _site_samples(
    metrics: pl.DataFrame,
    links: pl.DataFrame,
    methods_path: Path,
    method_edges_path: Path,
    call_sites_path: Path,
    source_zip: Path,
) -> tuple[dict, dict]:
    methods = pl.read_parquet(methods_path)
    method_edges = pl.read_parquet(method_edges_path)
    call_sites = pl.read_parquet(call_sites_path)
    metric_by_id = {
        row["node_id"]: row for row in metrics.iter_rows(named=True)
    }
    label_by_id = dict(zip(metrics["node_id"], metrics["label"], strict=True))
    method_by_key = {
        row["method_key"]: row for row in methods.iter_rows(named=True)
    }

    method_keys = [
        "java.base/java/lang/String#substring(II)Ljava/lang/String;",
        "java.base/java/lang/System#arraycopy(Ljava/lang/Object;ILjava/lang/Object;II)V",
        "java.base/java/lang/Runnable#run()V",
        "java.base/java/lang/String#<init>()V",
        "java.base/java/lang/Boolean#<clinit>()V",
        "java.base/com/sun/crypto/provider/DESKey#lambda$new$0([B)V",
    ]
    method_nodes = []
    for key in method_keys:
        method = method_by_key[key]
        metric = metric_by_id[method["method_id"]]
        method_nodes.append(
            {
                **_metric_sample(metric),
                "method_key": key,
                "source_file": method["source_file"],
                "first_line": method["first_line"],
                "last_line": method["last_line"],
                "flags": [
                    name
                    for name, present in (
                        ("constructor", method["is_constructor"]),
                        ("static initializer", method["is_static_init"]),
                        ("native", method["is_native"]),
                        ("abstract", method["is_abstract"]),
                        ("synthetic", method["is_synthetic"]),
                    )
                    if present
                ]
                or ["ordinary"],
            }
        )

    pair_rows = []
    for row in links.sort(["multiplicity", "src_id", "dst_id"], descending=[True, False, False]).head(8).iter_rows(named=True):
        pair_rows.append(
            {
                "caller": label_by_id[row["src_id"]],
                "callee": label_by_id[row["dst_id"]],
                "multiplicity": row["multiplicity"],
                "relation": row["relation"],
            }
        )

    call_rows = []
    for invoke_kind in ("STATIC", "SPECIAL", "VIRTUAL", "INTERFACE", "DYNAMIC"):
        candidates = (
            call_sites.filter(pl.col("invoke_kind") == invoke_kind)
            .with_columns(
                pl.col("caller_method_id").replace_strict(label_by_id).alias("caller"),
                pl.col("callee_method_id").replace_strict(label_by_id).alias("callee"),
            )
            .sort(["caller", "instruction_ordinal"])
        )
        row = candidates.row(0, named=True)
        call_rows.append(
            {
                "caller": row["caller"],
                "callee": row["callee"],
                "invoke_kind": row["invoke_kind"],
                "instruction_ordinal": row["instruction_ordinal"],
                "source_line": row["source_line"],
                "declared_target": (
                    f"{row['declared_owner']}#{row['declared_name']}"
                    f"{row['declared_descriptor']}"
                ),
                "resolution": row["resolution"],
            }
        )

    positive_rows = [_metric_sample(row) for row in heapq.nlargest(
        6,
        metrics.iter_rows(named=True),
        key=lambda row: (int(row["in_paths_source"]), -int(row["node_id"])),
    )]
    zero_labels = [
        "java.lang.String.contentEquals(Ljava/lang/StringBuffer;)Z",
        "java.lang.String.transform(Ljava/util/function/Function;)Ljava/lang/Object;",
        "java.lang.Thread.activeCount()I",
        "java.lang.Thread.getAllStackTraces()Ljava/util/Map;",
        "java.util.List.reversed()Ljava/util/SequencedCollection;",
        "java.lang.Math.asinh(D)D",
    ]
    zero_rows = [
        _metric_sample(metrics.filter(pl.col("label") == label).row(0, named=True))
        for label in zero_labels
    ]
    cycle_rows = [_metric_sample(row) for row in heapq.nlargest(
        6,
        metrics.filter(pl.col("is_path_cycle_boundary")).iter_rows(named=True),
        key=lambda row: (int(row["in_paths_source"]), -int(row["node_id"])),
    )]

    node_method = method_by_key[
        "java.base/java/lang/String#substring(II)Ljava/lang/String;"
    ]
    edge_caller_key = (
        "java.base/com/sun/crypto/provider/AEADBufferedStream#checkCapacity(I)V"
    )
    edge_caller = method_by_key[edge_caller_key]
    edge_call = call_sites.filter(
        (pl.col("caller_method_id") == edge_caller["method_id"])
        & (pl.col("declared_owner") == "jdk/internal/util/ArraysSupport")
        & (pl.col("declared_name") == "newLength")
    ).row(0, named=True)
    edge_callee = methods.filter(
        pl.col("method_id") == edge_call["callee_method_id"]
    ).row(0, named=True)
    extraction = {
        "node": {
            "source_path": "src/java.base/share/classes/java/lang/String.java",
            "source_lines": [node_method["first_line"] - 1, node_method["last_line"]],
            "source_excerpt": _source_excerpt(
                source_zip,
                node_method["module_name"],
                node_method["class_name"],
                node_method["source_file"],
                node_method["first_line"] - 1,
                node_method["last_line"],
            ),
            "classfile_fields": {
                "module": node_method["module_name"],
                "internal_class": node_method["class_name"],
                "name": node_method["method_name"],
                "descriptor": node_method["descriptor"],
                "access_flags": node_method["access_flags"],
            },
            "output": method_nodes[0],
        },
        "edge": {
            "source_path": (
                "src/java.base/share/classes/com/sun/crypto/provider/"
                "AEADBufferedStream.java"
            ),
            "source_lines": [edge_caller["first_line"] - 1, edge_caller["last_line"]],
            "source_excerpt": _source_excerpt(
                source_zip,
                edge_caller["module_name"],
                edge_caller["class_name"],
                edge_caller["source_file"],
                edge_caller["first_line"] - 1,
                edge_caller["last_line"],
            ),
            "bytecode_reference": {
                "invoke_kind": edge_call["invoke_kind"],
                "instruction_ordinal": edge_call["instruction_ordinal"],
                "source_line": edge_call["source_line"],
                "declared_owner": edge_call["declared_owner"],
                "declared_name": edge_call["declared_name"],
                "declared_descriptor": edge_call["declared_descriptor"],
                "resolution": edge_call["resolution"],
            },
            "output": {
                "caller_method_key": edge_caller_key,
                "callee_method_key": edge_callee["method_key"],
                "invoke_kind": edge_call["invoke_kind"],
                "multiplicity": method_edges.filter(
                    (pl.col("caller_method_id") == edge_caller["method_id"])
                    & (pl.col("callee_method_id") == edge_callee["method_id"])
                    & (pl.col("invoke_kind") == edge_call["invoke_kind"])
                )["callsite_count"][0],
            },
        },
    }
    return (
        {
            "method_nodes": method_nodes,
            "call_pairs": pair_rows,
            "call_occurrences": call_rows,
            "positive_path_nodes": positive_rows,
            "zero_path_nodes": zero_rows,
            "cycle_boundary_nodes": cycle_rows,
        },
        extraction,
    )


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
    samples = {}
    extraction_examples = {}
    sample_inputs = (
        args.methods,
        args.method_edges,
        args.call_sites,
        args.source_zip,
    )
    if args.site_json and not all(sample_inputs):
        raise ValueError(
            "--site-json requires --methods, --method-edges, --call-sites, and --source-zip"
        )
    if all(sample_inputs):
        samples, extraction_examples = _site_samples(
            metrics,
            links,
            args.methods,
            args.method_edges,
            args.call_sites,
            args.source_zip,
        )
    payload = {
        "schema_version": "1.2",
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
        "paper_reuse": _paper_reuse_analysis(metrics),
        "rank_shape": rank_shape,
        "top_nodes": top_rows,
        "samples": samples,
        "extraction_examples": extraction_examples,
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
            "paper": "https://arxiv.org/abs/cs/0508023v3",
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
