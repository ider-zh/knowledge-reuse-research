# knowledge-reuse-research

Reproducible research on declaration-level knowledge reuse in Lean 4 / mathlib.
The baseline experiment is pinned to mathlib `v4.32.1`; Lean's toolchain is read
from that checkout rather than duplicated by hand.

## Current status

Phase 0 (bootstrap) is in progress. Full-corpus extraction is intentionally
blocked until the pinned-version capability probe and exact golden dependency
tests pass.

## Bootstrap

Prerequisites: Git, Python 3.12+, `uv`, and network access for the initial
mathlib checkout and dependency downloads.

```bash
just doctor
just bootstrap
just probe
just golden
```

The remaining command surface is reserved by the experiment specification:
`inventory`, `extract-smoke`, `extract`, `normalize`, `validate`, `analyze`,
`report`, and `all`.

## Data policy

`vendor/`, `data/`, caches, and large generated artifacts are not committed.
Raw extraction data is immutable JSONL.zst; canonical analytical data is
Parquet; DuckDB databases are rebuildable caches.

