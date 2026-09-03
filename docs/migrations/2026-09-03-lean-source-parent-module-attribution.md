# Lean SOURCE parent-module attribution

`lean-source-graph-v2` strengthens the source endpoint rule used by the
declaration reuse graph. In v1, a non-null `.ilean` parent label entered the
graph whenever the name occurred in the pinned Environment. This could assign
a top-level command reference to an imported declaration with the same parent
label, even though that declaration was defined in another module.

Version 2 requires both persistent Environment identity and module agreement:

```text
parent_decl in Environment
and Environment[parent_decl].module = usage.module
```

The raw `.ilean` usage rows and their v1 checksums are unchanged. Normalized v2
artifacts are written under a new schema-version directory and are rebuildable
from those immutable raw rows. Rejected module mismatches are preserved in
`mismatched_parent_usages.parquet`; they are not silently treated as missing or
empty.

The pinned full snapshot contains nine mismatched positions belonging to three
parent labels. They include a top-level `to_additive existing` attribute command
whose parent label names `MulDistribMulAction` from another module. All v2 edge
counts, multiplicities, derived metrics, checksums, and public site evidence must
therefore be regenerated rather than copied from v1.
