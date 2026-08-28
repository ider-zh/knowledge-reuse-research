# Lean/mathlib workstream

Owns the nested `lean/LeanGraph` extractor, Lean fixtures, pinned mathlib
configuration, commands, SQL, and this adapter.
Do not change graph semantics, versions, golden expectations, or shard
composition without rerunning capability/golden gates and documenting checksum
compatibility. Data belongs under `data/lean_mathlib/<snapshot>/`; compact
results belong under `results/lean_mathlib_v1/`.
