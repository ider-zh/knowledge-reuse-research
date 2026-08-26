from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys

import polars as pl


ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data" / "raw" / "mathlib-v4.32.1" / "smoke" / "manifest.json"


def benchmark(worker_counts: list[int]) -> list[dict[str, object]]:
    rows = []
    for workers in worker_counts:
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "scripts.run_extract",
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
    metrics = ROOT / "results" / "metrics"
    metrics.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows).write_parquet(
        metrics / "extraction_benchmark.parquet", compression="zstd"
    )
    (ROOT / "results" / "extraction-benchmark.json").write_text(
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
