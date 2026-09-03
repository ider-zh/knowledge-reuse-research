#!/usr/bin/env python3
"""Test finite-library, component-size, and Erdos-Kac analogues on a JDK graph."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import polars as pl
from scipy import stats


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--methods", type=Path, required=True)
    parser.add_argument("--classes", type=Path, required=True)
    parser.add_argument("--call-sites", type=Path, required=True)
    parser.add_argument("--method-code", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--site-json", type=Path)
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--max-candidates", type=int, default=300)
    return parser.parse_args()


def _display_indices(count: int, limit: int = 180) -> np.ndarray:
    if count <= limit:
        return np.arange(count)
    return np.unique(
        np.rint(np.exp(np.linspace(0, math.log(count), limit))).astype(int) - 1
    )


def _component_size_analysis(methods: pl.DataFrame, calls: pl.DataFrame) -> dict:
    primary_calls = calls.filter(
        pl.col("invoke_kind").is_in(["STATIC", "SPECIAL"])
        & (pl.col("resolution") == "EXACT")
    )
    uses = primary_calls.group_by("callee_method_id").agg(pl.len().alias("uses"))
    ranked = (
        methods.select(
            "method_id", "method_key", "module_name", "class_name", "bytecode_length",
            "instruction_count", "has_code", "is_synthetic",
        )
        .join(uses, left_on="method_id", right_on="callee_method_id", how="inner")
        .filter(pl.col("has_code") & pl.col("bytecode_length").is_not_null())
        .sort(["uses", "method_key"], descending=[True, False])
        .with_row_index("rank", offset=1)
        .with_columns(
            (pl.col("bytecode_length").cast(pl.Int64) - 3).clip(lower_bound=0).alias(
                "gross_savings_bytes_per_use"
            )
        )
    )
    use_values = ranked["uses"].to_numpy().astype(float)
    size_values = ranked["bytecode_length"].to_numpy().astype(float)
    rho, rho_p = stats.spearmanr(np.log10(use_values), np.log10(size_values))
    ranks = ranked["rank"].to_numpy().astype(float)
    savings_bits = ranked["gross_savings_bytes_per_use"].to_numpy().astype(float) * 8
    identifier_min_bits = np.ceil(np.log2(np.maximum(ranks, 1)))
    lower_bound_consistency = float(np.mean(savings_bits >= identifier_min_bits))

    bin_count = 40
    edges = np.unique(np.rint(np.geomspace(1, ranked.height + 1, bin_count + 1)).astype(int))
    binned = []
    for start, stop in zip(edges[:-1], edges[1:], strict=True):
        subset = ranked.filter((pl.col("rank") >= start) & (pl.col("rank") < stop))
        if subset.is_empty():
            continue
        binned.append(
            {
                "rank_geometric_mean": float(math.sqrt(start * max(start, stop - 1))),
                "count": subset.height,
                "median_uses": float(subset["uses"].median()),
                "median_bytecode_length": float(subset["bytecode_length"].median()),
                "median_gross_savings_bytes": float(
                    subset["gross_savings_bytes_per_use"].median()
                ),
                "theoretical_min_identifier_bits": float(
                    math.log2(math.sqrt(start * max(start, stop - 1)))
                ),
            }
        )

    indices = _display_indices(ranked.height)
    rows = ranked.to_dicts()
    points = [
        {
            "rank": rows[index]["rank"],
            "uses": rows[index]["uses"],
            "bytecode_length": rows[index]["bytecode_length"],
            "gross_savings_bytes_per_use": rows[index]["gross_savings_bytes_per_use"],
            "method": rows[index]["method_key"],
        }
        for index in indices
    ]
    return {
        "definition": {
            "population": "concrete methods targeted by EXACT STATIC or SPECIAL bytecode calls",
            "component_size": "Code.code_length bytes",
            "use_count": "resolved bytecode invocation occurrences",
            "gross_savings_proxy": "max(Code.code_length - 3-byte invoke instruction, 0)",
            "identifier_boundary": (
                "ceil(log2(rank)) is a global theoretical minimum; JVM call sites use a "
                "16-bit class-local constant-pool index plus shared metadata"
            ),
        },
        "population": ranked.height,
        "call_sites": int(primary_calls.height),
        "spearman_log_use_vs_log_size": float(rho),
        "spearman_p_value": float(rho_p),
        "gross_savings_meets_log2_rank_fraction": lower_bound_consistency,
        "jvm_call_operand_bits": 16,
        "global_component_identifier_min_bits": math.ceil(math.log2(methods.height)),
        "binned_points": binned,
        "display_points": points,
    }


def _class_use_frame(
    methods: pl.DataFrame, classes: pl.DataFrame, calls: pl.DataFrame
) -> pd.DataFrame:
    caller = methods.select(
        pl.col("method_id").alias("caller_method_id"),
        pl.col("module_name").alias("caller_module"),
        pl.col("package_name").alias("caller_package"),
        pl.col("class_name").alias("caller_class"),
    )
    callee = methods.select(
        pl.col("method_id").alias("callee_method_id"),
        pl.col("module_name").alias("callee_module"),
        pl.col("package_name").alias("callee_package"),
        pl.col("class_name").alias("callee_class"),
    )
    detailed = calls.select("caller_method_id", "callee_method_id").join(
        caller, on="caller_method_id", how="inner", validate="m:1"
    ).join(callee, on="callee_method_id", how="inner", validate="m:1")
    base = classes.select(
        pl.col("module_name").alias("caller_module"),
        pl.col("class_name").alias("caller_class"),
        "classfile_size",
        "constant_pool_entries",
    )
    result = base
    scopes = {
        "cross_class": pl.col("caller_class") != pl.col("callee_class"),
        "cross_package": (
            (pl.col("caller_module") != pl.col("callee_module"))
            | (pl.col("caller_package") != pl.col("callee_package"))
        ),
        "cross_module": pl.col("caller_module") != pl.col("callee_module"),
    }
    for name, predicate in scopes.items():
        counts = (
            detailed.filter(predicate)
            .group_by("caller_module", "caller_class")
            .agg(
                pl.col("callee_method_id").n_unique().alias(f"{name}_distinct"),
                pl.len().alias(f"{name}_occurrences"),
            )
        )
        result = result.join(
            counts, on=["caller_module", "caller_class"], how="left", validate="1:1"
        )
    return result.fill_null(0).to_pandas()


def _conditional_normality(frame: pd.DataFrame, column: str) -> dict:
    size = frame["classfile_size"].to_numpy(dtype=float)
    counts = frame[column].to_numpy(dtype=float)
    quantiles = pd.qcut(size, q=20, duplicates="drop")
    working = pd.DataFrame({"size": size, "count": counts, "bin": quantiles})
    grouped = working.groupby("bin", observed=True)["count"].agg(["count", "mean", "std"])
    working = working.join(grouped[["mean", "std"]], on="bin")
    valid = (working["std"] > 0) & (working.groupby("bin", observed=True)["count"].transform("size") >= 100)
    z = ((working.loc[valid, "count"] - working.loc[valid, "mean"]) / working.loc[valid, "std"]).to_numpy()
    z = z[np.isfinite(z)]
    skewness = float(stats.skew(z, bias=False))
    excess_kurtosis = float(stats.kurtosis(z, fisher=True, bias=False))
    normaltest = stats.normaltest(z)
    anderson = stats.anderson(z, dist="norm")
    five_percent_index = list(anderson.significance_level).index(5.0)
    ordered = np.sort(z)
    theoretical = stats.norm.ppf((np.arange(ordered.size) + 0.5) / ordered.size)
    qq_r_squared = float(np.corrcoef(theoretical, ordered)[0, 1] ** 2)
    rho, _ = stats.spearmanr(np.log10(size), counts)
    slope, intercept, r_value, _, _ = stats.linregress(np.log10(size), np.log1p(counts))

    hist_counts, hist_edges = np.histogram(np.clip(z, -4, 4), bins=40, range=(-4, 4))
    qq_indices = _display_indices(ordered.size, 120)
    size_bins = []
    for interval, row in grouped.iterrows():
        subset = working[working["bin"] == interval]
        size_bins.append(
            {
                "size_median": float(subset["size"].median()),
                "program_count": int(row["count"]),
                "component_mean": float(row["mean"]),
                "component_stddev": float(row["std"]),
            }
        )
    consistent = abs(skewness) < 0.2 and abs(excess_kurtosis) < 0.5 and qq_r_squared > 0.99
    return {
        "program_count": int(frame.shape[0]),
        "positive_program_count": int(np.count_nonzero(counts)),
        "mean_distinct_components": float(np.mean(counts)),
        "median_distinct_components": float(np.median(counts)),
        "spearman_log_size_vs_components": float(rho),
        "log1p_component_vs_log10_size_slope": float(slope),
        "log1p_component_vs_log10_size_r_squared": float(r_value**2),
        "standardized_observation_count": int(z.size),
        "skewness": skewness,
        "excess_kurtosis": excess_kurtosis,
        "qq_r_squared": qq_r_squared,
        "dagostino_k2": float(normaltest.statistic),
        "dagostino_p_value": float(normaltest.pvalue),
        "anderson_statistic": float(anderson.statistic),
        "anderson_critical_5pct": float(anderson.critical_values[five_percent_index]),
        "pre_registered_shape_consistent": consistent,
        "size_bins": size_bins,
        "histogram": [
            {
                "z_left": float(hist_edges[index]),
                "z_right": float(hist_edges[index + 1]),
                "count": int(value),
            }
            for index, value in enumerate(hist_counts)
        ],
        "qq_points": [
            {"normal_quantile": float(theoretical[index]), "observed_z": float(ordered[index])}
            for index in qq_indices
        ],
    }


def _erdos_kac_analysis(
    methods: pl.DataFrame, classes: pl.DataFrame, calls: pl.DataFrame
) -> dict:
    frame = _class_use_frame(methods, classes, calls)
    scopes = {
        name: _conditional_normality(frame, f"{name}_distinct")
        for name in ("cross_class", "cross_package", "cross_module")
    }
    return {
        "definition": {
            "program_unit": "one classfile",
            "program_size": "serialized classfile bytes",
            "component_count": "distinct referenced callee methods outside the selected boundary",
            "conditioning": "20 classfile-size quantile bins; z-score within bins having >=100 programs",
            "pre_registered_shape_rule": "abs(skew)<0.2, abs(excess kurtosis)<0.5, Q-Q R^2>0.99",
        },
        "primary_scope": "cross_class",
        "scopes": scopes,
    }


def _fold_for(package: str, folds: int) -> int:
    return int.from_bytes(hashlib.sha256(package.encode()).digest()[:4], "big") % folds


def _candidate_allowed(pattern: tuple[str, ...]) -> bool:
    informative = (
        "ADD", "SUB", "MUL", "DIV", "REM", "FIELD", "INVOKE", "ARRAY",
        "CAST", "INSTANCEOF", "NEWARRAY", "COMPARE",
    )
    return any(any(fragment in opcode for fragment in informative) for opcode in pattern)


def _ngram_records(rows: list[dict], lengths: range):
    for row in rows:
        opcodes = row["opcodes"]
        sizes = row["instruction_sizes"]
        next_allowed_start: dict[tuple[str, ...], int] = {}
        for length in lengths:
            if len(opcodes) < length:
                continue
            rolling_bytes = sum(sizes[:length])
            for start in range(len(opcodes) - length + 1):
                if start:
                    rolling_bytes += sizes[start + length - 1] - sizes[start - 1]
                pattern = tuple(opcodes[start : start + length])
                if (
                    _candidate_allowed(pattern)
                    and start >= next_allowed_start.get(pattern, 0)
                ):
                    yield pattern, rolling_bytes, row
                    next_allowed_start[pattern] = start + length


def _mdl_fold(train: list[dict], test: list[dict], max_candidates: int) -> dict:
    counts: Counter[tuple[str, ...]] = Counter()
    byte_totals: Counter[tuple[str, ...]] = Counter()
    for pattern, byte_count, _ in _ngram_records(train, range(4, 9)):
        counts[pattern] += 1
        byte_totals[pattern] += byte_count
    scored = []
    for pattern, count in counts.items():
        if count < 20:
            continue
        mean_bytes = byte_totals[pattern] / count
        estimated = count * (mean_bytes - 3) - mean_bytes - 8
        if estimated > 0:
            scored.append((estimated, pattern, mean_bytes))
    scored.sort(reverse=True)
    selected = {pattern: mean_bytes for _, pattern, mean_bytes in scored[:max_candidates]}

    train_packages: defaultdict[tuple[str, ...], set[str]] = defaultdict(set)
    for pattern, _, row in _ngram_records(train, range(4, 9)):
        if pattern in selected:
            train_packages[pattern].add(row["package_name"])
    selected = {
        pattern: mean_bytes
        for pattern, mean_bytes in selected.items()
        if len(train_packages[pattern]) >= 3
    }

    test_counts: Counter[tuple[str, ...]] = Counter()
    test_bytes: Counter[tuple[str, ...]] = Counter()
    test_classes: defaultdict[tuple[str, ...], set[str]] = defaultdict(set)
    for pattern, byte_count, row in _ngram_records(test, range(4, 9)):
        if pattern in selected:
            test_counts[pattern] += 1
            test_bytes[pattern] += byte_count
            test_classes[pattern].add(f"{row['module_name']}/{row['class_name']}")

    results = []
    for pattern, definition_bytes in selected.items():
        occurrence_count = test_counts[pattern]
        link_count = len(test_classes[pattern])
        net = test_bytes[pattern] - 3 * occurrence_count - definition_bytes - 8 * link_count
        results.append(
            {
                "opcodes": list(pattern),
                "length": len(pattern),
                "train_occurrences": counts[pattern],
                "train_packages": len(train_packages[pattern]),
                "test_occurrences": occurrence_count,
                "test_classes": link_count,
                "heldout_net_savings_bytes": float(net),
            }
        )
    results.sort(key=lambda row: row["heldout_net_savings_bytes"], reverse=True)
    positive = [row for row in results if row["heldout_net_savings_bytes"] > 0]
    return {
        "train_methods": len(train),
        "test_methods": len(test),
        "selected_candidates": len(results),
        "positive_heldout_candidates": len(positive),
        "best_heldout_net_savings_bytes": positive[0]["heldout_net_savings_bytes"] if positive else 0,
        "top_candidates": results[:20],
    }


def _mdl_analysis(
    methods: pl.DataFrame, method_code: pl.DataFrame, folds: int, max_candidates: int
) -> dict:
    eligible = (
        method_code.join(
            methods.select(
                "method_id", "module_name", "package_name", "class_name",
                "instruction_count", "has_control_flow", "has_exception_handlers",
                "is_synthetic",
            ),
            on="method_id", how="inner", validate="1:1",
        )
        .filter(
            ~pl.col("has_control_flow")
            & ~pl.col("has_exception_handlers")
            & ~pl.col("is_synthetic")
            & pl.col("instruction_count").is_between(4, 512)
        )
    )
    rows = eligible.to_dicts()
    for row in rows:
        row["fold"] = _fold_for(row["package_name"], folds)
    fold_results = []
    for fold in range(folds):
        train = [row for row in rows if row["fold"] != fold]
        test = [row for row in rows if row["fold"] == fold]
        result = _mdl_fold(train, test, max_candidates)
        result["fold"] = fold
        fold_results.append(result)
    best_values = np.array(
        [row["best_heldout_net_savings_bytes"] for row in fold_results], dtype=float
    )
    return {
        "status": "exploratory MDL proxy; opcode macros are not verified Java APIs",
        "definition": {
            "eligible_methods": (
                "non-synthetic, straight-line, exception-free methods with 4..512 instructions"
            ),
            "candidate": (
                "normalized opcode n-gram of length 4..8 seen in >=3 training packages; "
                "occurrences of the same candidate cannot overlap within a method"
            ),
            "heldout_savings": (
                "fragment bytes - 3 bytes per macro reference - definition bytes - "
                "8 bytes per referencing class"
            ),
            "split": "deterministic package-hash cross-validation",
            "limitation": (
                "stack contracts, operands, semantic naming, access rules, and verifier-safe "
                "rewriting are not yet modeled"
            ),
        },
        "eligible_method_count": eligible.height,
        "folds": fold_results,
        "folds_with_positive_candidate": int(np.count_nonzero(best_values > 0)),
        "median_best_heldout_net_savings_bytes": float(np.median(best_values)),
    }


def main() -> int:
    args = parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    methods = pl.read_parquet(args.methods)
    classes = pl.read_parquet(args.classes)
    calls = pl.read_parquet(args.call_sites)
    method_code = pl.read_parquet(args.method_code)
    required_method_columns = {
        "bytecode_length", "instruction_count", "has_control_flow", "has_exception_handlers"
    }
    if not required_method_columns.issubset(methods.columns):
        raise ValueError("Phase 2 enriched method metrics are required")

    payload = {
        "schema_version": "1.0",
        "snapshot_id": "openjdk-jdk-28+13",
        "phase_1": {
            "status": "superseded",
            "reason": (
                "Phase 4 directly tests held-out description-length savings and Phase 5 "
                "tests temporal growth; the weaker within-snapshot vocabulary curve is omitted"
            ),
        },
        "phase_2": {
            "status": "complete",
            "methods": methods.height,
            "classes": classes.height,
            "methods_with_code": int(methods["has_code"].sum()),
            "total_bytecode_bytes": int(methods["bytecode_length"].fill_null(0).sum()),
            "total_classfile_bytes": int(classes["classfile_size"].sum()),
        },
        "phase_3_erdos_kac": _erdos_kac_analysis(methods, classes, calls),
        "phase_4_component_size": _component_size_analysis(methods, calls),
        "phase_4_mdl_incompleteness": _mdl_analysis(
            methods, method_code, args.folds, args.max_candidates
        ),
        "phase_5_cross_version": {
            "status": "pending",
            "reason": "cross-version snapshots are produced separately and merged later",
        },
    }
    output_path = args.output / "reuse_theorem_tests.json"
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    if args.site_json:
        args.site_json.parent.mkdir(parents=True, exist_ok=True)
        args.site_json.write_text(json.dumps(payload, ensure_ascii=False) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
