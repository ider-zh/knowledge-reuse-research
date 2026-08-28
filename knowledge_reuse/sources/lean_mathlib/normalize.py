from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import tomllib
from typing import Any

import polars as pl

from knowledge_reuse.sources.lean_mathlib.ingest import scan_raw_shards
from knowledge_reuse.sources.lean_mathlib.source_index import add_source_metrics


ROOT = pathlib.Path(__file__).resolve().parents[3]
CONFIG = tomllib.loads((ROOT / "configs" / "experiment-v1.toml").read_text())
INVENTORY_PATH = ROOT / "results" / "inventory.json"


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


def sanitize_expr_counts(frame: pl.LazyFrame) -> pl.LazyFrame:
    """Keep saturation explicit and exclude capped counts from quantitative analysis."""
    return frame.with_columns(
        pl.col("type_expr_nodes_saturated").fill_null(False),
        pl.col("value_expr_nodes_saturated").fill_null(False),
    ).with_columns(
        pl.when(pl.col("type_expr_nodes_saturated"))
        .then(None)
        .otherwise(pl.col("type_expr_nodes"))
        .alias("type_expr_nodes"),
        pl.when(pl.col("value_expr_nodes_saturated"))
        .then(None)
        .otherwise(pl.col("value_expr_nodes"))
        .alias("value_expr_nodes"),
    )


def normalize(run_kind: str) -> dict[str, Any]:
    snapshot = CONFIG["snapshot_id"]
    raw_dir = ROOT / "data" / "raw" / snapshot / run_kind
    output_dir = ROOT / "data" / "parquet" / snapshot / run_kind
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
            "type_expr_nodes_saturated",
            "value_expr_nodes",
            "value_expr_nodes_saturated",
            "type_const_unique",
            "value_const_unique",
            "source_start_line",
            "source_start_column",
            "source_end_line",
            "source_end_column",
        )
        .pipe(sanitize_expr_counts)
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
        .unique(subset=["snapshot_id", "src", "dst", "edge_type"], keep="first")
        .collect(engine="streaming")
        .sort("src", "dst", "edge_type")
    )
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
            "type_expr_nodes_saturated",
            "value_expr_nodes",
            "value_expr_nodes_saturated",
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
    audit_path = ROOT / "data" / "audit" / "modules.parquet"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    modules.write_parquet(audit_path, compression="zstd", statistics=True)
    manifest = {
        "schema_version": "normalized-manifest-v1",
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
    (ROOT / "results" / f"normalization-{run_kind}-summary.json").write_text(
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
