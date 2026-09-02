# Lean `.ilean` source-reference graph

`lean-source-graph-v1` changes the primary repeated-edge observation from
expanded Expr-tree paths to source locations resolved by Lean's `.ilean`
index. Existing `lean-graph-v2` raw and normalized artifacts remain immutable.

Nodes continue to come from the pinned Environment declaration extraction.
Attributed `.ilean` usages become `SOURCE` edges in the direction
consumer/parent declaration to resolved target declaration. One normalized row
represents a source-target pair; `multiplicity` is its number of distinct LSP
source ranges. Usages without `parentDecl` remain in
`unattributed_usages.parquet` and do not become declaration edges.

`SOURCE` is deliberately not presented as TYPE or VALUE. Expanded Expr
occurrences remain available only as a separate expression-sharing complexity
view and are not a source-reference count.
