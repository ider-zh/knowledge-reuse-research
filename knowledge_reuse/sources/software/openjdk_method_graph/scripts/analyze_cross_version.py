#!/usr/bin/env python3
"""Compare two normalized OpenJDK method graphs for vocabulary growth and reuse."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import polars as pl


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--older", type=Path, required=True)
    parser.add_argument("--newer", type=Path, required=True)
    parser.add_argument("--older-label", required=True)
    parser.add_argument("--newer-label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--merge-into", type=Path)
    return parser.parse_args()


def _snapshot(path: Path, label: str) -> tuple[dict, pl.DataFrame, pl.DataFrame]:
    methods = pl.read_parquet(path / "methods.parquet")
    classes = pl.read_parquet(path / "classes.parquet")
    calls = pl.read_parquet(path / "call_sites.parquet")
    frequencies = calls.group_by("callee_method_id").agg(pl.len().alias("uses"))
    ordered = frequencies.sort("uses", descending=True)["uses"].to_numpy().astype(float)
    ranks = np.arange(1, ordered.size + 1, dtype=float)
    log_rank = np.log10(ranks)
    log_use = np.log10(ordered)
    slope, intercept = np.polyfit(log_rank, log_use, 1)
    predicted = intercept + slope * log_rank
    r_squared = 1.0 - float(np.square(log_use - predicted).sum()) / float(
        np.square(log_use - log_use.mean()).sum()
    )
    manifest = json.loads((path / "graph_manifest.json").read_text(encoding="utf-8"))
    summary = {
        "label": label,
        "jmods": manifest["counts"]["jmods"],
        "classes": classes.height,
        "methods": methods.height,
        "methods_with_code": methods.filter(pl.col("has_code")).height,
        "bytecode_bytes": int(methods["bytecode_length"].fill_null(0).sum()),
        "resolved_call_sites": calls.height,
        "referenced_methods": frequencies.height,
        "reuse_rank_beta": float(-slope),
        "reuse_rank_r_squared": r_squared,
    }
    return summary, methods, calls


def _pct(newer: int, older: int) -> float:
    return (newer / older - 1.0) * 100.0


def main() -> int:
    args = parse_args()
    old_summary, old_methods, _ = _snapshot(args.older, args.older_label)
    new_summary, new_methods, new_calls = _snapshot(args.newer, args.newer_label)

    old_keys = set(old_methods["method_key"].to_list())
    new_keys = set(new_methods["method_key"].to_list())
    retained = old_keys & new_keys
    added = new_keys - old_keys
    removed = old_keys - new_keys

    new_key_map = new_methods.select("method_id", "method_key", "bytecode_length")
    caller_map = new_methods.select(
        pl.col("method_id").alias("caller_method_id"),
        pl.col("method_key").alias("caller_key"),
    )
    callee_map = new_key_map.rename(
        {"method_id": "callee_method_id", "method_key": "callee_key"}
    )
    added_calls = (
        new_calls.join(caller_map, on="caller_method_id", how="inner")
        .join(callee_map, on="callee_method_id", how="inner")
        .filter(pl.col("callee_key").is_in(added))
    )
    retained_to_added = added_calls.filter(pl.col("caller_key").is_in(retained))
    added_frequency = added_calls.group_by("callee_method_id").agg(pl.len().alias("uses"))
    retained_frequency = retained_to_added.group_by("callee_method_id").agg(
        pl.len().alias("uses")
    )
    retained_savings = (
        retained_frequency.join(
            new_key_map, left_on="callee_method_id", right_on="method_id", how="inner"
        )
        .with_columns(
            (pl.col("bytecode_length").cast(pl.Int64) - 3)
            .clip(lower_bound=0)
            .alias("bytes_per_use")
        )
        .with_columns((pl.col("uses") * pl.col("bytes_per_use")).alias("gross_bytes"))
    )

    comparison = {
        "status": "complete_two_snapshot_test",
        "definition": {
            "component_identity": "module/class#method(descriptor)",
            "growth_test": "declarations added and removed between official binary snapshots",
            "adoption_test": "JDK 28 resolved calls from retained method identities to added callees",
            "savings_proxy": "sum(max(new callee Code.code_length - 3, 0) * call occurrences)",
            "limitation": (
                "two snapshots cannot establish unbounded growth; retained method identity does not "
                "prove an unchanged implementation, and gross bytecode savings is not causal"
            ),
        },
        "snapshots": [old_summary, new_summary],
        "delta": {
            "classes_percent": _pct(new_summary["classes"], old_summary["classes"]),
            "methods_percent": _pct(new_summary["methods"], old_summary["methods"]),
            "bytecode_bytes_percent": _pct(
                new_summary["bytecode_bytes"], old_summary["bytecode_bytes"]
            ),
            "resolved_call_sites_percent": _pct(
                new_summary["resolved_call_sites"], old_summary["resolved_call_sites"]
            ),
            "retained_methods": len(retained),
            "added_methods": len(added),
            "removed_methods": len(removed),
            "net_methods": len(new_keys) - len(old_keys),
            "retention_fraction_of_older": len(retained) / len(old_keys),
        },
        "new_component_adoption": {
            "added_methods_referenced_anywhere": added_frequency.height,
            "calls_to_added_methods": added_calls.height,
            "added_methods_referenced_from_retained_callers": retained_frequency.height,
            "retained_caller_calls_to_added_methods": retained_to_added.height,
            "gross_savings_proxy_bytes": int(retained_savings["gross_bytes"].sum() or 0),
            "top_added_components": (
                retained_savings.sort(["uses", "method_key"], descending=[True, False])
                .select("method_key", "uses", "bytecode_length", "gross_bytes")
                .head(20)
                .to_dicts()
            ),
        },
        "interpretation": {
            "finite_snapshot_incomplete": (
                "supported as a finite longitudinal observation: the newer snapshot adds methods "
                "and retained method identities call some of them"
            ),
            "unbounded_component_supply": "not established by two versions",
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(comparison, indent=2), encoding="utf-8")
    if args.merge_into:
        report = json.loads(args.merge_into.read_text(encoding="utf-8"))
        report["phase_5_cross_version"] = comparison
        args.merge_into.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(comparison["delta"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
