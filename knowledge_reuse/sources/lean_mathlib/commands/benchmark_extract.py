from __future__ import annotations

import argparse
import json
import subprocess
import sys

import polars as pl

from knowledge_reuse.sources.lean_mathlib.layout import BENCHMARK_ROOT, ROOT, raw_root

MANIFEST = raw_root("mathlib-v4.32.1", "smoke") / "manifest.json"


def benchmark(worker_counts: list[int]) -> list[dict[str, object]]:
    rows = []
    for workers in worker_counts:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "knowledge_reuse.sources.lean_mathlib.commands.run_extract",
                "--smoke",
                "--force",
                "--workers",
                str(workers),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        if proc.returncode:
            raise RuntimeError(
                f"smoke extraction benchmark failed at {workers} workers:\n{proc.stderr}"
            )
        manifest = json.loads(MANIFEST.read_text())
        rows.append(
            {
                "worker_count": workers,
                "wall_time_seconds": manifest["wall_time_seconds"],
                "records_per_second": manifest["records_per_second"],
                "record_count": manifest["record_count"],
                "bytes_written": manifest["bytes_written"],
                "peak_child_rss_kib": manifest["peak_child_rss_kib"],
                "failed_retries": manifest["failed_retries"],
                "all_modules_ok": manifest["status_counts"]["ok"]
                == manifest["module_count"],
            }
        )
    BENCHMARK_ROOT.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(
        BENCHMARK_ROOT / "extraction.parquet", compression="zstd"
    )
    (BENCHMARK_ROOT / "extraction.json").write_text(
        json.dumps(
            {
                "schema_version": "extraction-benchmark-v1",
                "run_kind": "smoke",
                "rows": rows,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 2, 4, 8])
    args = parser.parse_args()
    if any(workers < 1 for workers in args.workers):
        parser.error("worker counts must be positive")
    print(json.dumps(benchmark(args.workers), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
