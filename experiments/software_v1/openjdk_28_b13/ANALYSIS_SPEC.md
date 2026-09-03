# OpenJDK Method Reuse Analysis Specification

Version: 1.2  
Graph: `software/openjdk/jdk-28+13/default`

## Research question

For every method in the closed OpenJDK Java-library call graph, how much
direct and transitive incoming reuse is represented by the graph? Does the
direct static-reference distribution reproduce the method used in Veldhuizen's
“Reuse and Zipf's Law,” and how does that result differ from the ranked path
distribution?

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

### Paper-aligned direct reuse

Veldhuizen counts static references to each library subroutine in a corpus of
executable and shared objects, sorts components by descending reference count,
and plots rank `n` against number of uses on log-log axes with `c*n^-1`
reference curves. The OpenJDK analogue is:

- component: one JVM method declaration;
- use: one resolved bytecode invocation call site targeting that method;
- reuse count: incoming edge multiplicity `U(v)=Σ_u m(u,v)`;
- ranking: methods with `U(v)>0`, sorted by descending `U(v)`;
- plot: `log10(n)` versus `log10(U(v))`, compared with `c/n`.

This calculation does not propagate callers' counts and does not use indirect
paths. No rank offset is applied. The paper starts its SunOS and Mac OS X
series at `n=50` to compensate for omitted machine instructions; the JDK corpus
uses a consistent method-only component unit and has no analogous omitted
higher-frequency category.

The fitted free exponent, fixed-`1/n` R², and log-space RMSE are supplemental
diagnostics; the paper's Figure 1 visually compares the empirical curves with a
family of `c*n^-1` lines and does not report those fit statistics.

### Path-shape analysis

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
  the 100 highest path-count methods, deterministic samples for each headline
  metric, and classfile-to-graph extraction examples;
- the same compact JSON can be written into the research-site public dataset.

The full per-node table is a rebuildable data artifact and is not committed.
Public site payload filenames are versioned when their required schema changes,
so cached JavaScript cannot consume an older incompatible JSON shape.
