"""Canonical filesystem layout for the Lean/mathlib source and experiment."""

from __future__ import annotations

import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[3]
SOURCE_ROOT = pathlib.Path(__file__).resolve().parent
LEAN_ROOT = SOURCE_ROOT / "lean"
SQL_ROOT = SOURCE_ROOT / "sql"

EXPERIMENT_ID = "lean_mathlib_v1"
EXPERIMENT_ROOT = ROOT / "experiments" / EXPERIMENT_ID
CONFIG_ROOT = EXPERIMENT_ROOT / "config"
FIXTURE_ROOT = EXPERIMENT_ROOT / "fixtures"
CONFIG_PATH = CONFIG_ROOT / "experiment-v1.toml"
EXCLUSIONS_PATH = CONFIG_ROOT / "exclusions.toml"

DATA_ROOT = ROOT / "data" / "lean_mathlib"
RESULTS_ROOT = ROOT / "results" / EXPERIMENT_ID
BENCHMARK_ROOT = RESULTS_ROOT / "benchmarks"
SCHEMA_ROOT = ROOT / "schemas" / "lean_mathlib"
COMPLEXITY_SCHEMA_VERSION = "expr-complexity-v2"
GRAPH_SCHEMA_VERSION = "lean-graph-v2"
SOURCE_GRAPH_SCHEMA_VERSION = "lean-source-graph-v1"


def snapshot_root(snapshot: str) -> pathlib.Path:
    return DATA_ROOT / snapshot


def raw_root(snapshot: str, run_kind: str) -> pathlib.Path:
    return snapshot_root(snapshot) / "raw" / GRAPH_SCHEMA_VERSION / run_kind


def complexity_raw_root(snapshot: str, run_kind: str) -> pathlib.Path:
    return snapshot_root(snapshot) / "raw" / COMPLEXITY_SCHEMA_VERSION / run_kind


def normalized_root(snapshot: str, run_kind: str) -> pathlib.Path:
    return snapshot_root(snapshot) / "normalized" / GRAPH_SCHEMA_VERSION / run_kind


def source_graph_raw_root(snapshot: str, run_kind: str) -> pathlib.Path:
    return snapshot_root(snapshot) / "raw" / SOURCE_GRAPH_SCHEMA_VERSION / run_kind


def source_graph_normalized_root(snapshot: str, run_kind: str) -> pathlib.Path:
    return snapshot_root(snapshot) / "normalized" / SOURCE_GRAPH_SCHEMA_VERSION / run_kind


def graph_audit_root(snapshot: str) -> pathlib.Path:
    return audit_root(snapshot) / GRAPH_SCHEMA_VERSION


def complexity_normalized_root(snapshot: str, run_kind: str) -> pathlib.Path:
    return snapshot_root(snapshot) / "normalized" / COMPLEXITY_SCHEMA_VERSION / run_kind


def audit_root(snapshot: str) -> pathlib.Path:
    return snapshot_root(snapshot) / "audit"


def run_results_root(run_kind: str) -> pathlib.Path:
    if run_kind not in {"smoke", "full"}:
        raise ValueError(f"unsupported run kind: {run_kind}")
    return RESULTS_ROOT / "runs" / run_kind
