"""Normalize the immutable expr-complexity-v2 raw sidecar."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import tomllib
from typing import Any

import polars as pl

from knowledge_reuse.sources.lean_mathlib.layout import (
    COMPLEXITY_SCHEMA_VERSION,
    CONFIG_PATH,
    ROOT,
    complexity_normalized_root,
    complexity_raw_root,
    normalized_root,
    run_results_root,
)

CONFIG = tomllib.loads(CONFIG_PATH.read_text())

COMPLEXITY_RAW_SCHEMA = {
    "record": pl.String,
    "snapshot": pl.String,
    "name": pl.String,
    "module": pl.String,
    "has_value": pl.Boolean,
    "type_expr_tree_occurrences": pl.UInt64,
    "type_expr_unique_ptr_nodes": pl.UInt64,
    "type_expr_dag_arcs": pl.UInt64,
    "type_expr_max_depth": pl.UInt64,
    "value_expr_tree_occurrences": pl.UInt64,
    "value_expr_unique_ptr_nodes": pl.UInt64,
    "value_expr_dag_arcs": pl.UInt64,
    "value_expr_max_depth": pl.UInt64,
    "status": pl.String,
    "decl_count": pl.UInt64,
    "edge_count": pl.UInt64,
    "warning_count": pl.UInt64,
    "error": pl.String,
    "duration_seconds": pl.Float64,
    "return_code": pl.Int32,
    "parse_error_count": pl.UInt64,
}


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def select_graph_complexity(
    raw_complexity: pl.DataFrame, graph_nodes: pl.DataFrame
) -> tuple[pl.DataFrame, int]:
    """Select graph-canonical provenance while rejecting conflicting aliases."""
    if raw_complexity.select("name", "module").n_unique() != raw_complexity.height:
        raise ValueError("duplicate (name, module) records in expression-complexity sidecar")
    metric_columns = [
        column
        for column in raw_complexity.columns
        if column not in {"snapshot_id", "name", "module"}
    ]
    conflicting_aliases = (
        raw_complexity.group_by("name")
        .agg(pl.col(column).n_unique().alias(column) for column in metric_columns)
        .filter(pl.any_horizontal(pl.col(column) > 1 for column in metric_columns))
    )
    if conflicting_aliases.height:
        raise ValueError(
            "same-name records from isolated module imports disagree on complexity"
        )
    complexity = (
        graph_nodes.select("name", "module")
        .join(raw_complexity, on=["name", "module"], how="inner", validate="1:1")
        .select(raw_complexity.columns)
        .sort("name")
    )
    if complexity.height != graph_nodes.height or set(complexity["name"]) != set(
        graph_nodes["name"]
    ):
        raise ValueError("expression-complexity sidecar does not match normalized graph nodes")
    return complexity, raw_complexity.height - complexity.height


def normalize_complexity(run_kind: str) -> dict[str, Any]:
    snapshot = CONFIG["snapshot_id"]
    paths = sorted(complexity_raw_root(snapshot, run_kind).glob("*.jsonl.zst"))
    if not paths:
        raise FileNotFoundError("no expression-complexity raw shards")
    raw = pl.scan_ndjson(paths, schema=COMPLEXITY_RAW_SCHEMA)
    raw_complexity = (
        raw.filter(pl.col("record") == "complexity")
        .select(
            pl.col("snapshot").alias("snapshot_id"),
            "name",
            "module",
            "has_value",
            "type_expr_tree_occurrences",
            "type_expr_unique_ptr_nodes",
            "type_expr_dag_arcs",
            "type_expr_max_depth",
            "value_expr_tree_occurrences",
            "value_expr_unique_ptr_nodes",
            "value_expr_dag_arcs",
            "value_expr_max_depth",
        )
        .collect(engine="streaming")
    )
    graph_nodes = pl.read_parquet(normalized_root(snapshot, run_kind) / "nodes.parquet")
    complexity, alias_rows = select_graph_complexity(raw_complexity, graph_nodes)
    joined = graph_nodes.select("name", "has_value", "type_expr_nodes", "value_expr_nodes").join(
        complexity,
        on="name",
        how="inner",
        suffix="_complexity",
        validate="1:1",
    )
    if not joined["has_value"].equals(joined["has_value_complexity"]):
        raise ValueError("has_value disagrees between graph and complexity sidecar")
    if not joined["type_expr_nodes"].equals(joined["type_expr_tree_occurrences"]):
        raise ValueError("type tree-occurrence values disagree with the immutable graph corpus")
    value_mismatch = joined.filter(
        ~(
            pl.col("value_expr_nodes").eq_missing(
                pl.col("value_expr_tree_occurrences")
            )
        )
    )
    if value_mismatch.height:
        raise ValueError("value tree-occurrence values disagree with the immutable graph corpus")
    output_dir = complexity_normalized_root(snapshot, run_kind)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "nodes.parquet"
    complexity.write_parquet(output_path, compression="zstd", statistics=True)
    manifest = {
        "schema_version": COMPLEXITY_SCHEMA_VERSION,
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "rows": complexity.height,
        "path": str(output_path.relative_to(ROOT)),
        "sha256": file_sha256(output_path),
        "null_counts": {
            column: complexity[column].null_count() for column in complexity.columns
        },
        "integrity_checks": {
            "node_identity_exact": True,
            "has_value_exact": True,
            "legacy_tree_occurrences_exact": True,
            "same_name_alias_metrics_exact": True,
        },
        "raw_same_name_alias_rows": alias_rows,
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    result_path = run_results_root(run_kind) / "complexity-normalization-summary.json"
    result_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    print(
        json.dumps(
            normalize_complexity("smoke" if args.smoke else "full"),
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
