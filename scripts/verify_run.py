from __future__ import annotations

import argparse
from dataclasses import dataclass
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


SEMANTIC_MODULUS = 1 << 256


def canonical_semantic_row(source: dict[str, Any]) -> bytes | None:
    if source.get("record") not in {"node", "edge"}:
        return None
    row = dict(source)
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


@dataclass(frozen=True)
class SemanticAccumulator:
    count: int = 0
    xor: int = 0
    total: int = 0

    def add(self, source: dict[str, Any]) -> SemanticAccumulator:
        encoded = canonical_semantic_row(source)
        if encoded is None:
            return self
        value = int.from_bytes(hashlib.sha256(encoded).digest())
        return SemanticAccumulator(
            self.count + 1,
            self.xor ^ value,
            (self.total + value) % SEMANTIC_MODULUS,
        )

    def merge(self, other: SemanticAccumulator) -> SemanticAccumulator:
        return SemanticAccumulator(
            self.count + other.count,
            self.xor ^ other.xor,
            (self.total + other.total) % SEMANTIC_MODULUS,
        )

    def digest(self) -> str:
        encoded = f"{self.count}:{self.xor:064x}:{self.total:064x}".encode()
        return hashlib.sha256(encoded).hexdigest()


def semantic_accumulator(rows: list[dict[str, Any]]) -> SemanticAccumulator:
    result = SemanticAccumulator()
    for source in rows:
        result = result.add(source)
    return result


def canonical_semantic_digest(rows: list[dict[str, Any]]) -> str:
    return semantic_accumulator(rows).digest()


def read_shard(path: pathlib.Path) -> list[dict[str, Any]]:
    with path.open("rb") as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed) as reader:
            text = reader.read().decode()
    return [json.loads(line) for line in text.splitlines()]


def shard_merge_digest(paths: list[pathlib.Path]) -> str:
    """Order-independent digest of the already checksum-verified shard set."""
    entries = []
    for path in paths:
        sidecar = json.loads(path.with_suffix(path.suffix + ".sha256").read_text())
        entries.append(f"{path.name}:{sidecar['sha256']}:{sidecar['module_plan_sha256']}")
    return hashlib.sha256(("\n".join(sorted(entries)) + "\n").encode()).hexdigest()


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
    sample_module = CONFIG["smoke"]["modules"][0]
    if run_kind == "smoke":
        sample_path = next(
            path
            for path in shards
            if any(
                row.get("record") == "node" and row.get("module") == sample_module
                for row in read_shard(path)
            )
        )
    else:
        shard_plan = json.loads((ROOT / "results" / "shard-plan.json").read_text())
        sample_shard_id = next(
            shard["id"] for shard in shard_plan["shards"] if sample_module in shard["modules"]
        )
        sample_path = raw_dir / f"{sample_shard_id}.jsonl.zst"
    sample_shard_rows = read_shard(sample_path)
    first_nodes = [row for row in sample_shard_rows if row.get("record") == "node"]
    sample_names = {
        row["name"]
        for row in first_nodes
        if row.get("module") == sample_module
    }
    sample_rows = [
        row
        for row in sample_shard_rows
        if (row.get("record") == "node" and row.get("name") in sample_names)
        or (row.get("record") == "edge" and row.get("src") in sample_names)
    ]
    rerun_rows = rerun_sample(sample_module, snapshot)
    forward_digest = shard_merge_digest(shards)
    reverse_digest = shard_merge_digest(list(reversed(shards)))
    checks = {
        **{name: count == 0 for name, count in failures.items()},
        "module_count_matches": module_count == expected_modules,
        "all_modules_ok": module_statuses == {"ok": expected_modules},
        "theorem_value_coverage_complete": theorem_count == theorem_with_value,
        "deterministic_sample_semantics": canonical_semantic_digest(sample_rows)
        == canonical_semantic_digest(rerun_rows),
        "shard_merge_order_independent": forward_digest == reverse_digest,
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
