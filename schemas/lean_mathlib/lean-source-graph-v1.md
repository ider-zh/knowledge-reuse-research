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

Usages without a parent declaration remain in a separate unattributed artifact
and do not become declaration edges. The graph does not claim TYPE/VALUE
classification, transitive dependency, runtime call frequency, or expanded
Expr-tree occurrence counts.
