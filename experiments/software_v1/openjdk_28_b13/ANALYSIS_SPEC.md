# OpenJDK Method Reuse Analysis Specification

Version: 1.0  
Graph: `software/openjdk/jdk-28+13/default`

## Research question

For every method in the closed OpenJDK Java-library call graph, how much
direct and transitive incoming reuse is represented by the graph, and does the
ranked distribution resemble Zipf's law or a curve derived from prime numbers?

## Metrics

For a directed caller-to-callee pair `u → v` with call-site multiplicity
`m(u,v)`, the analysis reports:

- **direct unique callers**: the number of distinct incoming caller pairs;
- **direct call occurrences**: `Σ m(u,v)` over incoming pairs;
- **indirect incoming paths**: the number of paths of length at least two;
- **all incoming paths**: direct call occurrences plus indirect paths.

Distinct routes remain distinct. Edge multiplicities multiply along a route
and alternative routes add. Counts use arbitrary-precision integers; decimal
strings are authoritative and `log10` values exist only for ranking and
visualization.

## Cycle boundary

All nodes in a strongly connected component of more than one node, and every
node with a self-loop, are cycle boundaries. An arrival at such a node counts,
but no path is extended from it. Direct edges are always counted, including
edges inside or leaving a cyclic component. This rule makes the propagated
graph acyclic and the path count finite.

This is a deliberately conservative interpretation of “stop at a cycle.” It
does not enumerate simple paths within a strongly connected component.

## Rank-shape comparison

Nodes with positive all-incoming-path counts are sorted by their exact integer
count. Zero-count nodes remain in population statistics but cannot appear on a
logarithmic rank curve.

Two fixed decreasing templates are compared in `log10` space:

- Zipf: `P(r) = 10^a / r`;
- reciprocal exact prime: `P(r) = 10^a / p_r`, where `p_r` is the r-th
  prime.

Each template fits only the intercept `a`. RMSE and R² are reported for all
positive observations and for the highest one percent. A free power-law rank
fit estimates the empirical exponent `β`; Zipf corresponds to `β = 1`.

The prime sequence itself increases and is not a candidate for a descending
rank curve. Its reciprocal is used only as a negative-control shape. Relative
fit cannot establish a prime-generating mechanism.

## Outputs

- `node_incoming_paths.parquet`: one row for every graph node;
- `reuse_analysis.json`: full-population summaries, rank fits, display points,
  and the 100 highest path-count methods;
- the same compact JSON can be written into the research-site public dataset.

The full per-node table is a rebuildable data artifact and is not committed.
