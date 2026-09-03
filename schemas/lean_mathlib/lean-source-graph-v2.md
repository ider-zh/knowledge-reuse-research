# Lean resolved source-reference graph v2

Version 2 retains the v1 atomic `.ilean` usage format and SOURCE-edge meaning,
but strengthens source declaration attribution. A resolved source location
becomes a declaration edge only when all of the following hold:

1. `.ilean` supplies a non-null `parent_decl` label;
2. that label identifies a persistent declaration in the pinned Environment;
3. the declaration's defining module equals the module recorded by the `.ilean`
   file containing the source location.

The third condition prevents a top-level command from being attributed to a
same-named declaration imported from another module. Such positions are stored
in `mismatched_parent_usages.parquet` with both the source module and resolved
parent declaration module; they do not become edges. Missing parent labels and
labels absent from the Environment remain separately preserved as in v1.

An accepted atomic usage is still identified by:

```text
(snapshot_id, module, parent_decl, target_module, target_decl,
 start_line, start_character, end_line, end_character)
```

The normalized edge table contains one row per `(src_id, dst_id)`, with
`edge_type = SOURCE`. Its `multiplicity` is the number of accepted distinct
resolved source ranges for that pair. Edge direction remains consumer
declaration to referenced declaration. Raw v1 usage artifacts remain immutable;
v2 normalization is fully rebuildable from them.

Derived multiplicity-weighted paths retain the v1 cycle-boundary rule. They are
route-combination diagnostics, not independent consumer counts or workload.
