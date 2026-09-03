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
The base edge table does not claim TYPE/VALUE classification, runtime call
frequency, or expanded Expr-tree occurrence counts. Transitive paths are a
separate derived metric with the cycle rule below; they are not additional raw
edges.

## Derived incoming path count

`source_graph_metrics/node_metrics.parquet` adds `in_paths_source`, an exact
direct-plus-indirect incoming path count over internal declaration nodes. Edge
multiplicity is preserved: if an edge has multiplicity `m`, every extendable
prefix path produces `m` distinct longer paths, while the edge itself
contributes `m` direct paths. For an acyclic node `v` this is equivalent to:

```text
P(v) = Σ(u → v) multiplicity(u,v) × (1 + extendable_paths(u))
```

Cycles are detected as strongly connected components. Every direct edge,
including a self-loop or an edge from a cyclic node, remains counted. A path
that reaches a cyclic component is terminal and is not extended through or
beyond that component. This rule prevents infinitely many repeated walks while
retaining the observed direct graph.

Because an exact path count can exceed 64-bit integers, `in_paths_source` is a
decimal string. `in_paths_source_log10` is a sortable numeric companion, not a
replacement or saturation of the exact value. `is_path_cycle_boundary` records
whether the node belongs to a terminal cyclic component. This derived metric is
not used as the primary direct-reuse measure in Zipf or concentration results.
