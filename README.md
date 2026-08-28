# knowledge-reuse-research

Reproducible research on declaration-level knowledge reuse in Lean 4 / mathlib.
The baseline experiment is pinned to mathlib `v4.32.1`; Lean's toolchain is read
from that checkout rather than duplicated by hand.

This is now a multi-source research monorepo. Lean/mathlib is the first adapter;
Wikipedia and open-source software graph workstreams have isolated namespaces
and experiment folders. Shared cross-system contracts and ownership rules are
documented in [`docs/architecture.md`](docs/architecture.md).

## Current status

The pinned capability probe, exact golden dependency gate, deterministic
inventory/sharding, resumable extraction, Parquet normalization, DuckDB audit,
statistical analysis, and offline report pipeline are implemented. The compact
result summaries identify whether a run is the smoke corpus or the full corpus;
do not interpret smoke estimates as mathlib-wide findings.

## Bootstrap

Prerequisites: Git, Python 3.12+, `uv`, `just`, and network access for the
initial mathlib checkout and dependency downloads.

```bash
just doctor
just bootstrap
just probe
just golden
just inventory
```

Run the cheap end-to-end validation path first:

```bash
just extract-smoke
just normalize-smoke
just validate-smoke
just analyze-smoke
just report-smoke
```

Then reproduce the formal full-corpus result:

```bash
just extract       # resumable; checksummed shards are skipped
just normalize
just validate      # hard gate before interpreting results
just analyze
just report
```

`just all` executes bootstrap through report in dependency order. Extraction
worker scaling can be measured with `just benchmark-extract` (1, 2, 4, and 8
workers on the frozen smoke module list). The v1 default is 8 workers, selected
from the recorded benchmark; lower it with `--workers` on memory-constrained
machines.

The final full-corpus offline artifact is
`results/lean_mathlib_v1/runs/full/report/report_standalone.html`. Smoke and full
artifacts are isolated under `runs/smoke/` and `runs/full/`; each run owns its
metrics, tables, report, stage summaries, identity, and checksums.

## Data policy

`vendor/`, `data/`, caches, and large generated artifacts are not committed.
Each source writes to `data/<source>/<snapshot>/`, while compact outputs use
`results/<experiment_id>/`. Raw extraction data is immutable JSONL.zst;
canonical analytical data is Parquet; DuckDB databases are rebuildable caches.

## Semantics and interpretation

Edges point from a consumer declaration to a dependency. TYPE and VALUE edges
are retained separately, and reuse is the target's unique-source indegree.
Extraction uses Lean's elaborated environment with pinned-version `import all`;
source text is used only for range-based length metrics, never dependency
identity. Tail claims are based on fitted-model comparisons, not visual log-log
linearity. `H*ref` is explicitly an empirical operational proxy, not a claim to
Veldhuizen's theoretical entropy H.
