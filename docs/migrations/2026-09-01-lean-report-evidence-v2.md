# Lean report evidence and provenance migration

Date: 2026-09-01

## Scope

This migration changes derived Lean/mathlib metrics, report evidence, and future
raw-manifest provenance. Existing raw graph and expression-complexity shards are
not modified.

## Derived-analysis changes

- `definition_to_definition` is now an explicit graph population alongside the
  existing theorem/definition views.
- Negative-binomial coefficient uncertainty uses an HC1 sandwich covariance
  estimate. Pearson dispersion is reported as a model diagnostic.
- Because the model uses `log1p(length)`, the reported `x -> 2x` effect is now
  evaluated exactly at the observed median `x`; it is no longer presented as a
  baseline-independent `exp(beta * log(2))` effect.
- Domain examples are selected deterministically from unique dependency pairs.

All affected files under `results/lean_mathlib_v1/runs/*/metrics/`, `tables/`,
and `report/` are rebuildable from versioned code and immutable normalized data.

## Report changes

- First-use definitions now precede headline values for Lean declarations,
  rank-tail beta, Gini, and `H*ref`, with authoritative Lean/Veldhuizen links.
- The power-law tail overlay is scaled to the empirical probability mass at
  `xmin`.
- The domain heatmap selects the most connected domains deterministically rather
  than taking an alphabetical prefix.
- TYPE, VALUE, and ALL-union edge counts and a node-to-edge evidence chain are
  shown explicitly.
- Graph completeness and code-provenance completeness are separate audit states.

## Provenance compatibility

Historical raw manifests in this snapshot do not contain the extractor Git
revision or executable checksum. The rebuilt report therefore marks extractor
provenance as incomplete while retaining the independently passed capability,
golden, and graph-completeness gates. It does not infer a historical revision
from the current checkout.

Future extraction shard checksum sidecars bind both the module plan and the
extractor executable SHA-256. A shard created before this migration is not a
valid cache hit under the new runner. Future raw manifests also record extractor
commit, dirty state, executable SHA-256, and configuration SHA-256.

