"""Lean raw JSONL.zst ingestion."""

from __future__ import annotations

import pathlib

import polars as pl


RAW_SCHEMA = {
    "record": pl.String,
    "snapshot": pl.String,
    "name": pl.String,
    "module": pl.String,
    "kind": pl.String,
    "has_value": pl.Boolean,
    "type_expr_nodes": pl.UInt64,
    "value_expr_nodes": pl.UInt64,
    "type_const_unique": pl.UInt32,
    "value_const_unique": pl.UInt32,
    "source_start_line": pl.UInt32,
    "source_start_column": pl.UInt32,
    "source_end_line": pl.UInt32,
    "source_end_column": pl.UInt32,
    "src": pl.String,
    "dst": pl.String,
    "edge_type": pl.String,
    "multiplicity": pl.UInt64,
    "status": pl.String,
    "decl_count": pl.UInt64,
    "edge_count": pl.UInt64,
    "warning_count": pl.UInt64,
    "error": pl.String,
    "duration_seconds": pl.Float64,
    "return_code": pl.Int32,
    "parse_error_count": pl.UInt64,
}


def scan_raw_shards(raw_dir: pathlib.Path) -> pl.LazyFrame:
    paths = sorted(raw_dir.glob("*.jsonl.zst"))
    if not paths:
        raise FileNotFoundError(f"no raw shards under {raw_dir}")
    return pl.scan_ndjson(paths, schema=RAW_SCHEMA)
