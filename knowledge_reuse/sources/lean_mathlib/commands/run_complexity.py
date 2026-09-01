"""Extract immutable expression-complexity sidecars without rebuilding graph edges."""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import resource
import subprocess
import time

from knowledge_reuse.sources.lean_mathlib.commands.run_extract import (
    LAKE,
    RUNNER_CONFIG,
    ShardResult,
    file_sha256,
    select_shards,
    write_shard,
)
from knowledge_reuse.sources.lean_mathlib.layout import (
    COMPLEXITY_SCHEMA_VERSION,
    CONFIG_PATH,
    ROOT,
    audit_root,
    complexity_raw_root,
    run_results_root,
)

EXTRACTOR = ROOT / ".lake" / "build" / "bin" / "lean-graph-complexity"


def run_complexity(smoke: bool, workers: int, force: bool) -> dict[str, object]:
    subprocess.run([LAKE, "build", "lean-graph-complexity"], cwd=ROOT, check=True)
    extractor_sha256 = file_sha256(EXTRACTOR)
    extractor_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    repository_dirty = bool(
        subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        ).stdout.strip()
    )
    snapshot = RUNNER_CONFIG["snapshot_id"]
    run_kind = "smoke" if smoke else "full"
    raw_dir = complexity_raw_root(snapshot, run_kind)
    log_dir = audit_root(snapshot) / COMPLEXITY_SCHEMA_VERSION / run_kind / "logs"
    shards = select_shards(smoke, RUNNER_CONFIG)
    started_at = datetime.datetime.now(datetime.UTC)
    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                write_shard,
                snapshot,
                shard,
                raw_dir,
                log_dir,
                force,
                EXTRACTOR,
            )
            for shard in shards
        ]
        results: list[ShardResult] = [
            future.result() for future in concurrent.futures.as_completed(futures)
        ]
    results.sort(key=lambda result: result.shard_id)
    wall_time = time.perf_counter() - started
    audits = sorted(
        (audit for result in results for audit in result.module_audits),
        key=lambda audit: audit["module"],
    )
    record_count = sum(result.record_count for result in results)
    manifest: dict[str, object] = {
        "schema_version": COMPLEXITY_SCHEMA_VERSION,
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "extractor_commit": extractor_commit,
        "extractor_repository_dirty": repository_dirty,
        "extractor_sha256": extractor_sha256,
        "config_sha256": file_sha256(CONFIG_PATH),
        "worker_count": workers,
        "started_at": started_at.isoformat(),
        "finished_at": datetime.datetime.now(datetime.UTC).isoformat(),
        "shard_count": len(results),
        "module_count": sum(len(shard["modules"]) for shard in shards),
        "status_counts": {
            status: sum(audit["status"] == status for audit in audits)
            for status in ("ok", "partial", "failed", "excluded")
        },
        "wall_time_seconds": wall_time,
        "records_per_second": record_count / wall_time if wall_time else None,
        "record_count": record_count,
        "bytes_written": sum(result.bytes_written for result in results),
        "peak_child_rss_kib": resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss,
        "failed_retries": sum(result.failed_retries for result in results),
        "shards": [result.__dict__ | {"module_audits": None} for result in results],
    }
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    result_path = run_results_root(run_kind) / "complexity-extraction-summary.json"
    result_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    failed = manifest["status_counts"]["failed"] + manifest["status_counts"]["partial"]
    if failed:
        raise RuntimeError(f"complexity extraction has {failed} failed/partial modules")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--workers", type=int)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    workers = args.workers or RUNNER_CONFIG["default_workers"]
    if workers < 1:
        parser.error("--workers must be positive")
    print(json.dumps(run_complexity(args.smoke, workers, args.force), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
