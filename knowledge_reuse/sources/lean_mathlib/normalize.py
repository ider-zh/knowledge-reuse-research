from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import tomllib
from typing import Any

import polars as pl

from knowledge_reuse.sources.lean_mathlib.ingest import scan_raw_shards
from knowledge_reuse.sources.lean_mathlib.layout import (
    CONFIG_PATH,
    RESULTS_ROOT,
    ROOT,
    audit_root,
    normalized_root,
    raw_root,
    run_results_root,
)
from knowledge_reuse.sources.lean_mathlib.source_index import add_source_metrics


CONFIG = tomllib.loads(CONFIG_PATH.read_text())
INVENTORY_PATH = RESULTS_ROOT / "inventory.json"


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory_frame() -> pl.DataFrame:
    inventory = json.loads(INVENTORY_PATH.read_text())
    return pl.DataFrame(inventory["modules"]).select(
        "module", "source_file", "domain", pl.col("status").alias("inventory_status")
    )


def generated_expr() -> pl.Expr:
    pattern = (
        r"(^_private\.|\._|\.rec(On)?$|\.casesOn$|\.noConfusion|\.inj(Eq)?$|"
        r"\.ctorIdx$|\.sizeOf|\._sizeOf_)"
    )
    return pl.col("name").str.contains(pattern)


def null_statistics(frame: pl.DataFrame) -> dict[str, int]:
    return {column: frame[column].null_count() for column in frame.columns}


def canonicalize_weighted_edges(raw_edges: pl.DataFrame) -> pl.DataFrame:
    edge_key = ["snapshot_id", "src", "dst", "edge_type"]
    if raw_edges["multiplicity"].null_count():
        raise ValueError("lean-graph-v2 requires non-null edge multiplicity")
    if raw_edges.filter(pl.col("multiplicity") < 1).height:
        raise ValueError("lean-graph-v2 edge multiplicity must be positive")
    conflicting = (
        raw_edges.group_by(edge_key)
        .agg(pl.col("multiplicity").n_unique().alias("multiplicity_variants"))
        .filter(pl.col("multiplicity_variants") > 1)
    )
    if conflicting.height:
        raise ValueError(
            "duplicate typed-edge keys disagree on multiplicity; declaration identity is ambiguous"
        )
    return raw_edges.unique(subset=edge_key, keep="first").sort("src", "dst", "edge_type")


def normalize(run_kind: str) -> dict[str, Any]:
    snapshot = CONFIG["snapshot_id"]
    raw_dir = raw_root(snapshot, run_kind)
    output_dir = normalized_root(snapshot, run_kind)
    output_dir.mkdir(parents=True, exist_ok=True)
    raw = scan_raw_shards(raw_dir)
    metadata = inventory_frame().lazy()

    nodes = (
        raw.filter(pl.col("record") == "node")
        .select(
            pl.col("snapshot").alias("snapshot_id"),
            "name",
            "module",
            "kind",
            "has_value",
            "type_expr_nodes",
            "value_expr_nodes",
            "type_const_unique",
            "value_const_unique",
            "source_start_line",
            "source_start_column",
            "source_end_line",
            "source_end_column",
        )
        .unique(subset=["snapshot_id", "name"], keep="first")
        .join(metadata, on="module", how="left")
        .with_columns(
            (pl.col("kind") == "theorem").alias("is_theorem"),
            pl.col("kind").is_in(["definition", "opaque"]).alias("is_definition"),
            generated_expr().alias("is_generated"),
            pl.col("name").str.contains(r"(^_private\.|\._)").alias("is_internal"),
        )
        .collect(engine="streaming")
        .sort("name")
    )
    nodes = add_source_metrics(nodes, ROOT / "vendor" / "mathlib4")
    raw_edges = (
        raw.filter(pl.col("record") == "edge")
        .select(
            pl.col("snapshot").alias("snapshot_id"),
            "src",
            "dst",
            "edge_type",
            "multiplicity",
        )
        .collect(engine="streaming")
        .sort("src", "dst", "edge_type")
    )
    raw_edges = canonicalize_weighted_edges(raw_edges)
    all_names = (
        pl.concat(
            [nodes.select("name"), raw_edges.select(pl.col("src").alias("name")), raw_edges.select(pl.col("dst").alias("name"))]
        )
        .unique()
        .sort("name")
        .with_row_index("node_id")
        .with_columns(pl.col("node_id").cast(pl.UInt64))
    )
    nodes = (
        nodes.join(all_names, on="name", how="left")
        .select(
            "snapshot_id",
            "node_id",
            "name",
            "module",
            "source_file",
            "domain",
            "kind",
            "is_theorem",
            "is_definition",
            "is_generated",
            "is_internal",
            "has_value",
            "source_bytes",
            "source_lines",
            "source_tokens",
            "type_expr_nodes",
            "value_expr_nodes",
            "type_const_unique",
            "value_const_unique",
        )
        .sort("node_id")
    )
    internal_names = nodes.select("name")
    external_nodes = (
        all_names.join(internal_names, on="name", how="anti")
        .with_columns(
            pl.lit(snapshot).alias("snapshot_id"),
            pl.lit("not_in_extracted_corpus").alias("external_reason"),
        )
        .select("snapshot_id", "node_id", "name", "external_reason")
        .sort("node_id")
    )
    src_ids = all_names.rename({"name": "src", "node_id": "src_id"})
    dst_ids = all_names.rename({"name": "dst", "node_id": "dst_id"})
    edges = (
        raw_edges.join(src_ids, on="src", how="left", validate="m:1")
        .join(dst_ids, on="dst", how="left", validate="m:1")
        .select("snapshot_id", "src_id", "dst_id", "edge_type", "multiplicity")
        .sort("src_id", "dst_id", "edge_type")
    )
    modules = (
        raw.filter(pl.col("record") == "audit")
        .select(
            pl.col("snapshot").alias("snapshot_id"),
            "module",
            "status",
            "duration_seconds",
            "decl_count",
            "edge_count",
            "warning_count",
            pl.col("error").alias("error_text"),
        )
        .collect(engine="streaming")
        .join(inventory_frame(), on="module", how="left")
        .select(
            "snapshot_id",
            "module",
            "source_file",
            "domain",
            "status",
            "duration_seconds",
            "decl_count",
            "edge_count",
            "warning_count",
            "error_text",
        )
        .sort("module")
    )

    frames = {
        "nodes": nodes,
        "edges": edges,
        "external_nodes": external_nodes,
        "modules": modules,
    }
    artifacts: dict[str, Any] = {}
    for name, frame in frames.items():
        path = output_dir / f"{name}.parquet"
        frame.write_parquet(path, compression="zstd", statistics=True)
        artifacts[name] = {
            "path": str(path.relative_to(ROOT)),
            "rows": frame.height,
            "sha256": file_sha256(path),
            "null_counts": null_statistics(frame),
        }
    audit_path = audit_root(snapshot) / CONFIG["schema_version"] / "modules.parquet"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    modules.write_parquet(audit_path, compression="zstd", statistics=True)
    manifest = {
        "schema_version": "normalized-manifest-v1",
        "graph_schema_version": CONFIG["schema_version"],
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "generated_heuristic": (
            "name matches private/auxiliary/recursor/cases/noConfusion/injection/ctorIdx/sizeOf patterns"
        ),
        "source_length_status": "declaration_ranges_with_nulls_for_unranged_generated_declarations",
        "artifacts": artifacts,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    run_dir = run_results_root(run_kind)
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "normalization-summary.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    manifest = normalize("smoke" if args.smoke else "full")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
