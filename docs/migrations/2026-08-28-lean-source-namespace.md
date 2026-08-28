# Lean/mathlib source namespace migration

The experiment was not yet published, so the temporary Lean v1 compatibility
layout was removed before adding Wikipedia and software pipelines.

## Path mapping

| Previous path | Canonical path |
|---|---|
| `LeanGraph/` | `knowledge_reuse/sources/lean_mathlib/lean/LeanGraph/` |
| `scripts/` | `knowledge_reuse/sources/lean_mathlib/commands/` |
| `sql/` | `knowledge_reuse/sources/lean_mathlib/sql/` |
| `configs/` | `experiments/lean_mathlib_v1/config/` |
| `fixtures/golden/` | `experiments/lean_mathlib_v1/fixtures/golden/` |
| `schemas/lean-graph-v1.*` | `schemas/lean_mathlib/lean-graph-v1.*` |
| `data/raw/<snapshot>/` | `data/lean_mathlib/<snapshot>/raw/` |
| `data/parquet/<snapshot>/` | `data/lean_mathlib/<snapshot>/normalized/` |
| `results/` | `results/lean_mathlib_v1/` and `runs/<run_kind>/` |

The move does not change compressed shard bytes or shard sidecar checksums.
Manifest path fields and the full raw-manifest checksum were updated because
their serialized path strings changed. All future source adapters must start in
the namespaced layout; no legacy compatibility package remains. Smoke and full
metrics/reports were separated after the migration exposed that their previous
shared directories allowed one run to overwrite the other.
