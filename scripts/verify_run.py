from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import shutil
import subprocess
import tomllib
from typing import Any

import duckdb
import zstandard


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = tomllib.loads((ROOT / "configs" / "experiment-v1.toml").read_text())
LAKE = shutil.which("lake") or str(pathlib.Path.home() / ".elan" / "bin" / "lake")
EXTRACTOR = ROOT / ".lake" / "build" / "bin" / "lean-graph-extract"


def canonical_semantic_digest(rows: list[dict[str, Any]]) -> str:
    semantic = []
    for source in rows:
        if source.get("record") not in {"node", "edge"}:
            continue
        row = dict(source)
        if row["record"] == "node":
            row.setdefault("type_expr_nodes_saturated", False)
            row.setdefault("value_expr_nodes_saturated", False if row.get("has_value") else None)
        semantic.append(row)
    encoded = sorted(
        json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        for row in semantic
    )
    return hashlib.sha256(("\n".join(encoded) + "\n").encode()).hexdigest()


def read_shard(path: pathlib.Path) -> list[dict[str, Any]]:
    with path.open("rb") as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed) as reader:
            text = reader.read().decode()
    return [json.loads(line) for line in text.splitlines()]


def rerun_sample(module: str, snapshot: str) -> list[dict[str, Any]]:
    proc = subprocess.run(
        [LAKE, "env", str(EXTRACTOR), snapshot, module],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return [json.loads(line) for line in proc.stdout.splitlines()]


def validate(run_kind: str) -> dict[str, Any]:
    snapshot = CONFIG["snapshot_id"]
    parquet_dir = ROOT / "data" / "parquet" / snapshot / run_kind
    raw_dir = ROOT / "data" / "raw" / snapshot / run_kind
    cache_path = ROOT / "data" / "cache" / "analysis.duckdb"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(cache_path))
    try:
        for name in ("nodes", "edges", "external_nodes", "modules"):
            path = (parquet_dir / f"{name}.parquet").as_posix().replace("'", "''")
            con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM read_parquet('{path}')")
        failures = dict(con.execute((ROOT / "sql" / "validation.sql").read_text()).fetchall())
        module_statuses = dict(
            con.execute("SELECT status, count(*) FROM modules GROUP BY status ORDER BY status").fetchall()
        )
        module_count = con.execute("SELECT count(*) FROM modules").fetchone()[0]
        expected_modules = (
            len(CONFIG["smoke"]["modules"])
            if run_kind == "smoke"
            else json.loads((ROOT / "results" / "inventory.json").read_text())["summary"]["included"]
        )
        theorem_count, theorem_with_value = con.execute(
            "SELECT count(*), count(*) FILTER (WHERE has_value) FROM nodes WHERE is_theorem"
        ).fetchone()
        node_count = con.execute("SELECT count(*) FROM nodes").fetchone()[0]
        edge_count = con.execute("SELECT count(*) FROM edges").fetchone()[0]
        external_count = con.execute("SELECT count(*) FROM external_nodes").fetchone()[0]
        null_rates = {
            row[0]: row[1] / node_count if node_count else None
            for row in con.execute(
                """
                SELECT column_name,
                       CASE column_name
                         WHEN 'source_bytes' THEN count(*) FILTER (WHERE source_bytes IS NULL)
                         WHEN 'source_lines' THEN count(*) FILTER (WHERE source_lines IS NULL)
                         WHEN 'source_tokens' THEN count(*) FILTER (WHERE source_tokens IS NULL)
                         WHEN 'value_expr_nodes' THEN count(*) FILTER (WHERE value_expr_nodes IS NULL)
                       END AS null_count
                FROM (VALUES ('source_bytes'), ('source_lines'), ('source_tokens'), ('value_expr_nodes')) t(column_name), nodes
                GROUP BY column_name
                """
            ).fetchall()
        }
    finally:
        con.close()

    shards = sorted(raw_dir.glob("*.jsonl.zst"))
    raw_rows = [read_shard(path) for path in shards]
    flat_forward = [row for rows in raw_rows for row in rows]
    flat_reverse = [row for rows in reversed(raw_rows) for row in rows]
    first_nodes = [row for row in raw_rows[0] if row.get("record") == "node"]
    sample_module = first_nodes[0]["module"]
    # A smoke shard contains exactly one module; declaration names need not share
    # the module prefix (for example, a module may extend an existing namespace).
    sample_rows = raw_rows[0]
    rerun_rows = rerun_sample(sample_module, snapshot)
    checks = {
        **{name: count == 0 for name, count in failures.items()},
        "module_count_matches": module_count == expected_modules,
        "all_modules_ok": module_statuses == {"ok": expected_modules},
        "theorem_value_coverage_complete": theorem_count == theorem_with_value,
        "deterministic_sample_semantics": canonical_semantic_digest(sample_rows)
        == canonical_semantic_digest(rerun_rows),
        "shard_merge_order_independent": canonical_semantic_digest(flat_forward)
        == canonical_semantic_digest(flat_reverse),
    }
    result = {
        "schema_version": "data-quality-v1",
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "passed": all(checks.values()),
        "checks": checks,
        "failure_counts": failures,
        "module_status_counts": module_statuses,
        "expected_module_count": expected_modules,
        "extracted_module_count": module_count,
        "extraction_completeness": module_count / expected_modules if expected_modules else None,
        "node_count": node_count,
        "edge_count": edge_count,
        "external_node_count": external_count,
        "theorem_count": theorem_count,
        "theorem_with_value_count": theorem_with_value,
        "null_rates": null_rates,
        "determinism_sample_module": sample_module,
    }
    metrics_dir = ROOT / "results" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    (metrics_dir / "data_quality.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    (ROOT / "results" / f"validation-{run_kind}-summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    result = validate("smoke" if args.smoke else "full")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
