# Lean expression complexity sidecar v2

This immutable sidecar adds complementary complexity measurements to every
declaration in a pinned Lean environment. It is keyed one-to-one by
`(snapshot, name)` and does not alter the lean-graph-v1 node or edge corpus.

For both the declaration type and an available value/proof expression:

- `*_expr_unique_ptr_nodes` counts distinct in-memory `Lean.Expr` objects
  reachable from the expression root. It measures the stored DAG under the
  pinned runtime and is not a semantic invariant across Lean versions.
- `*_expr_dag_arcs` counts child positions of those distinct objects. If one
  child is referenced twice, both references count as arcs.
- `*_expr_max_depth` is the longest root-to-leaf path, with a leaf having depth
  one. Shared subexpressions do not multiply depth.
- `*_expr_tree_occurrences` counts constructor occurrences after conceptually
  expanding shared references at every use site. The count is exact and may be
  much larger than the stored DAG.

The four Value fields are null exactly when `has_value` is false. Null means no
value/proof expression was exposed by the pinned environment; it is not zero.
Type fields are always present. Normalization rejects sidecars whose declaration
identity, `has_value`, or legacy tree-occurrence fields disagree with the
immutable graph corpus.

Some generated declarations can be emitted under more than one isolated module
import while sharing the same global name. Normalization requires every such
alias to have identical complexity fields, then selects the `(name, module)`
provenance already chosen by the immutable normalized graph. It never resolves
conflicting metrics by keeping an arbitrary row.
