# Explicit saturation for Lean expression-size metrics

Lean proof terms are DAGs. Expanding sharing to compute a tree-occurrence count can
require work far beyond the number of stored expression objects. Starting with this
migration, raw Lean node records include `type_expr_nodes_saturated` and
`value_expr_nodes_saturated`.

- `false` means the corresponding tree-occurrence count is exact.
- `true` means the extractor reached its fixed work or `UInt64` bound. The numeric
  raw value is `UInt64.max`, never an empty or missing proof body.
- Older raw shards have no saturation fields and are interpreted as `false`.
- Determinism validation applies the same legacy-to-current default adapter before
  hashing, so resumed runs can safely combine immutable pre-migration shards with
  newly extracted shards.
- Normalization retains the flags but converts saturated numeric counts to null so
  regressions, correlations, bins, and figures do not treat a bound as an observation.
- TYPE and VALUE dependency edges are unaffected and remain complete because Lean's
  dedicated constant traversal runs independently of the size metric.

This is a backward-compatible extension of `lean-graph-v1`: the new raw properties
are optional in the JSON schema so checksum-complete pre-migration shards remain
readable and rebuildable.
