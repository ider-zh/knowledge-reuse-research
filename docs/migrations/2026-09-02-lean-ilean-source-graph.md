# Lean `.ilean` source-reference graph

`lean-source-graph-v1` changes the primary repeated-edge observation from
expanded Expr-tree paths to source locations resolved by Lean's `.ilean`
index. Existing `lean-graph-v2` raw and normalized artifacts remain immutable.

Nodes continue to come from the pinned Environment declaration extraction.
Attributed `.ilean` usages become `SOURCE` edges in the direction
consumer/parent declaration to resolved target declaration. One normalized row
represents a source-target pair; `multiplicity` is its number of distinct LSP
source ranges. Usages without `parentDecl` remain in
`unparented_usages.parquet` and do not become declaration edges. A non-null
`.ilean` parent label that has no corresponding Environment declaration (such
as an `example` context) is preserved in `unresolved_parent_usages.parquet`
and likewise excluded from declaration-to-declaration edges.

`SOURCE` is deliberately not presented as TYPE or VALUE. Expanded Expr
occurrences remain available only as a separate expression-sharing complexity
view and are not a source-reference count.

## Full-snapshot validation

The graph contains 1,837,322 declaration pairs and 2,384,758 attributed source
occurrences. The occurrence total equals the sum of edge multiplicities.
Distinct repeated locations are retained: 353,628 pairs have multiplicity
greater than one. The graph also retains 2,580 self-loop pairs, representing
4,714 source occurrences.

Of 2,496,585 resolved source locations, 109,575 have no parent declaration and
2,252 have a parent label that is absent from the extracted Environment. These
records remain available in separate artifacts and do not become graph edges.
A second full run reproduced every normalized artifact checksum.

For `DFunLike.coe`, `.ilean` contains 387 source locations in 227 modules. One
location belongs to a private `_eval` parent label absent from the Environment;
the graph therefore contains 386 attributed occurrences from 370 declaration
nodes, while retaining the excluded location as evidence.
