# Lean expression complexity v2 migration

The existing `lean-graph-v1` raw corpus remains byte-for-byte immutable. This
migration adds a separately checksummed `expr-complexity-v2` sidecar under the
same source and snapshot namespace. It can be rebuilt and normalized without
rewriting graph nodes or edges.

Golden fixture `golden-v2` extends the prior exact node, edge, and expanded-tree
checks with unique pointer-node, DAG-arc, and maximum-depth checks. The legacy
tree-occurrence checksum is unchanged. Consumers join the sidecar one-to-one on
declaration name and must reject identity, value-availability, or expanded-tree
disagreement.

For generated same-name declarations observed through multiple isolated module
imports, normalization first proves all complexity fields identical and then
uses the canonical `(name, module)` already present in `lean-graph-v1`. The full
v4.32.1 sidecar contains 422 such additional alias rows and zero conflicting
aliases.
