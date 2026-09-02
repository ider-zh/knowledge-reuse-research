# Lean resolved source-reference graph v1

This graph replaces expanded Expr-tree edge multiplicity with source locations
resolved by Lean's `.ilean` reference index. Nodes remain named declarations
from the pinned `Environment` extraction.

An atomic usage is identified by:

```text
(snapshot_id, module, parent_decl, target_module, target_decl,
 start_line, start_character, end_line, end_character)
```

The normalized edge table contains one row per `(src_id, dst_id)` with
`edge_type = SOURCE`. Its positive `multiplicity` is the number of distinct
resolved source locations for the pair. Positions use LSP UTF-16 coordinates.

The `.ilean` constant key's module component is retained as `target_module` in
the atomic usage record. Lean normally obtains it from the Environment module
index, but falls back to the current module when no index is available. It is
therefore a module hint, not part of node identity. External-node metadata
retains every observed hint rather than selecting an arbitrary one.

Usages without a parent declaration remain in `unparented_usages.parquet`.
Usages whose `.ilean` parent label is absent from the extracted Environment
(for example an `example` command context) remain in
`unresolved_parent_usages.parquet`. Neither class becomes a declaration edge.
The graph does not claim TYPE/VALUE classification, transitive dependency,
runtime call frequency, or expanded Expr-tree occurrence counts.
