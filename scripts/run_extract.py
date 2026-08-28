from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import hashlib
import io
import json
import pathlib
import resource
import shutil
import subprocess
import tempfile
import time
import tomllib
from dataclasses import dataclass
from typing import Any

import zstandard


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "experiment-v1.toml"
RUNNER_CONFIG = tomllib.loads(CONFIG_PATH.read_text())
INVENTORY_PATH = ROOT / "results" / "inventory.json"
PLAN_PATH = ROOT / "results" / "shard-plan.json"
LAKE = shutil.which("lake") or str(pathlib.Path.home() / ".elan" / "bin" / "lake")
EXTRACTOR = ROOT / ".lake" / "build" / "bin" / "lean-graph-extract"


@dataclass(frozen=True)
class ShardResult:
    shard_id: str
    status: str
    raw_path: str
    sha256: str
    bytes_written: int
    record_count: int
    duration_seconds: float
    module_audits: list[dict[str, Any]]
    resumed: bool
    failed_retries: int


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def module_plan_sha256(modules: list[str]) -> str:
    return hashlib.sha256(("\n".join(modules) + "\n").encode()).hexdigest()


def valid_cached_shard(path: pathlib.Path, expected_plan_sha256: str) -> str | None:
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    if not path.is_file() or not checksum_path.is_file():
        return None
    try:
        sidecar = json.loads(checksum_path.read_text())
    except json.JSONDecodeError:
        return None
    content_sha256 = sidecar.get("sha256")
    if sidecar.get("module_plan_sha256") != expected_plan_sha256:
        return None
    return content_sha256 if file_sha256(path) == content_sha256 else None


def read_cached_shard_metadata(path: pathlib.Path) -> tuple[int, list[dict[str, Any]]]:
    """Strictly rebuild record/audit metadata from an immutable cached shard."""
    record_count = 0
    audits: list[dict[str, Any]] = []
    with path.open("rb") as compressed:
        with zstandard.ZstdDecompressor().stream_reader(compressed) as reader:
            with io.TextIOWrapper(reader, encoding="utf-8") as text:
                for line_number, line in enumerate(text, 1):
                    try:
                        row = json.loads(line)
                    except json.JSONDecodeError as error:
                        raise ValueError(f"invalid cached shard {path}, line {line_number}: {error}") from error
                    record_count += 1
                    if row.get("record") == "audit":
                        audits.append(row)
    return record_count, audits


def run_modules(
    snapshot: str, modules: list[str], log_path: pathlib.Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], bool]:
    started = time.perf_counter()
    proc = subprocess.run(
        [LAKE, "env", str(EXTRACTOR), snapshot, *modules],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    duration = time.perf_counter() - started
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(proc.stderr)
    rows: list[dict[str, Any]] = []
    parse_errors = []
    for index, line in enumerate(proc.stdout.splitlines(), 1):
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as error:
            parse_errors.append(f"line {index}: {error}")
    audits = [row for row in rows if row.get("record") == "audit"]
    expected = set(modules)
    observed = {str(audit.get("module")) for audit in audits}
    complete = proc.returncode == 0 and observed == expected and len(audits) == len(modules)
    per_module_duration = duration / len(modules)
    for audit in audits:
        audit["duration_seconds"] = per_module_duration
        audit["shard_process_duration_seconds"] = duration
        audit["return_code"] = proc.returncode
        audit["parse_error_count"] = len(parse_errors)
        if (parse_errors or not complete) and audit["status"] == "ok":
            audit["status"] = "partial"
            audit["error"] = "; ".join(parse_errors) or "incomplete shard process"
    return rows, audits, complete


def run_module(
    snapshot: str, module: str, log_dir: pathlib.Path
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows, audits, complete = run_modules(snapshot, [module], log_dir / f"{module}.log")
    if complete:
        return rows, audits[0]
    audit = audits[0] if len(audits) == 1 else {
        "record": "audit",
        "snapshot": snapshot,
        "module": module,
        "status": "failed",
        "decl_count": sum(row.get("record") == "node" for row in rows),
        "edge_count": sum(row.get("record") == "edge" for row in rows),
        "warning_count": 0,
        "error": f"expected one successful audit record, found {len(audits)}",
        "duration_seconds": 0.0,
        "return_code": 1,
        "parse_error_count": 0,
    }
    if audit not in rows:
        rows.append(audit)
    return rows, audit


def write_shard(
    snapshot: str,
    shard: dict[str, Any],
    raw_dir: pathlib.Path,
    log_dir: pathlib.Path,
    force: bool,
) -> ShardResult:
    started = time.perf_counter()
    target = raw_dir / f"{shard['id']}.jsonl.zst"
    plan_sha256 = module_plan_sha256(shard["modules"])
    if not force and (checksum := valid_cached_shard(target, plan_sha256)):
        record_count, audits = read_cached_shard_metadata(target)
        expected_modules = set(shard["modules"])
        observed_modules = {str(audit.get("module")) for audit in audits}
        if len(audits) != len(shard["modules"]) or observed_modules != expected_modules:
            raise ValueError(
                f"cached shard {target} has incomplete audits: "
                f"expected {len(expected_modules)}, observed {len(audits)}"
            )
        return ShardResult(
            shard["id"],
            "resumed",
            str(target.relative_to(ROOT)),
            checksum,
            target.stat().st_size,
            record_count,
            time.perf_counter() - started,
            audits,
            True,
            0,
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    audits: list[dict[str, Any]] = []
    failed_retries = 0
    record_count = 0
    modules = shard["modules"]
    extraction_config = RUNNER_CONFIG.get("extraction", {})
    chunk_size = (
        extraction_config.get("profiled_chunk_size", len(modules))
        if shard["id"] in extraction_config.get("profiled_chunk_shards", [])
        else len(modules)
    )
    groups = [modules[index : index + chunk_size] for index in range(0, len(modules), chunk_size)]
    rows = []
    for group_index, group in enumerate(groups):
        group_rows, group_audits, complete = run_modules(
            snapshot, group, log_dir / f"{shard['id']}-part-{group_index:03d}.log"
        )
        if complete:
            rows.extend(group_rows)
            audits.extend(group_audits)
            continue
        failed_retries += len(group)
        for module in group:
            module_rows, audit = run_module(snapshot, module, log_dir)
            rows.extend(module_rows)
            audits.append(audit)
    with tempfile.NamedTemporaryFile(dir=target.parent, suffix=".tmp", delete=False) as tmp:
        temp_path = pathlib.Path(tmp.name)
        with zstandard.ZstdCompressor(level=6).stream_writer(tmp, closefd=False) as writer:
            for row in rows:
                writer.write(
                    json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
                    + b"\n"
                )
                record_count += 1
    temp_path.replace(target)
    checksum = file_sha256(target)
    target.with_suffix(target.suffix + ".sha256").write_text(
        json.dumps({"sha256": checksum, "module_plan_sha256": plan_sha256}, sort_keys=True) + "\n"
    )
    statuses = {audit["status"] for audit in audits}
    status = "ok" if statuses == {"ok"} else "partial" if "ok" in statuses else "failed"
    return ShardResult(
        shard["id"],
        status,
        str(target.relative_to(ROOT)),
        checksum,
        target.stat().st_size,
        record_count,
        time.perf_counter() - started,
        audits,
        False,
        failed_retries,
    )


def select_shards(smoke: bool, config: dict[str, Any]) -> list[dict[str, Any]]:
    if smoke:
        modules = config["smoke"]["modules"]
        return [
            {"id": f"smoke-{index:05d}", "modules": [module]}
            for index, module in enumerate(modules)
        ]
    plan = json.loads(PLAN_PATH.read_text())
    return plan["shards"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    config = tomllib.loads(CONFIG_PATH.read_text())
    workers = args.workers or config["default_workers"]
    if workers < 1:
        parser.error("--workers must be positive")
    if not INVENTORY_PATH.exists() or not PLAN_PATH.exists():
        raise SystemExit("missing inventory/shard plan; run inventory and make_shards first")
    subprocess.run([LAKE, "build", "lean-graph-extract"], cwd=ROOT, check=True)
    snapshot = config["snapshot_id"]
    run_kind = "smoke" if args.smoke else "full"
    raw_dir = ROOT / "data" / "raw" / snapshot / run_kind
    log_dir = ROOT / "data" / "audit" / snapshot / run_kind / "logs"
    shards = select_shards(args.smoke, config)
    started_at = datetime.datetime.now(datetime.UTC)
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(write_shard, snapshot, shard, raw_dir, log_dir, args.force)
            for shard in shards
        ]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    results.sort(key=lambda result: result.shard_id)
    wall_time = time.perf_counter() - started
    finished_at = datetime.datetime.now(datetime.UTC)
    audits = sorted(
        (audit for result in results for audit in result.module_audits),
        key=lambda audit: audit["module"],
    )
    audit_path = ROOT / "data" / "audit" / snapshot / f"modules-{run_kind}.jsonl"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in audits))
    record_count = sum(result.record_count for result in results)
    bytes_written = sum(result.bytes_written for result in results)
    raw_manifest = {
        "schema_version": "raw-manifest-v1",
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "worker_count": workers,
        "started_at": started_at.isoformat(),
        "finished_at": finished_at.isoformat(),
        "shard_count": len(results),
        "module_count": sum(len(shard["modules"]) for shard in shards),
        "status_counts": {
            status: sum(audit["status"] == status for audit in audits)
            for status in ("ok", "partial", "failed", "excluded")
        },
        "wall_time_seconds": wall_time,
        "records_per_second": record_count / wall_time if wall_time else None,
        "record_count": record_count,
        "bytes_written": bytes_written,
        "peak_child_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "failed_retries": sum(result.failed_retries for result in results),
        "shards": [result.__dict__ | {"module_audits": None} for result in results],
    }
    manifest_path = raw_dir / "manifest.json"
    manifest_path.write_text(json.dumps(raw_manifest, indent=2, sort_keys=True) + "\n")
    summary_path = ROOT / "results" / f"extraction-{run_kind}-summary.json"
    summary_path.write_text(json.dumps(raw_manifest, indent=2, sort_keys=True) + "\n")
    print(json.dumps(raw_manifest, indent=2, sort_keys=True))
    failed = raw_manifest["status_counts"]["failed"] + raw_manifest["status_counts"]["partial"]
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
