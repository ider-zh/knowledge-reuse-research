# OpenJDK Method Reuse Analysis Specification

Version: 1.3  
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

## Paper-theorem tests: Phase 2–5

Phase 1 (a single-snapshot vocabulary saturation curve) is **superseded**. It
is skipped because Phase 4 directly asks whether held-out programs admit a new
description-shortening component, while Phase 5 observes component vocabulary
change over time.

### Phase 2: enriched extraction

For every concrete method, retain bytecode length, instruction count, max
stack/locals, control-flow and exception-handler flags, plus opcode and encoded
instruction-size sequences. For every classfile, retain serialized size and
constant-pool entry count. These are attributes; node and edge semantics do not
change.

### Phase 3: conditional component-count shape

One classfile is the observable program unit. Its component count is the number
of distinct resolved callee methods beyond a selected class, package, or module
boundary. Program size is serialized classfile bytes. Split observations into
20 size-quantile bins, z-score component counts within bins of at least 100
classes, and evaluate the pooled values. The pre-registered descriptive shape
rule is `|skew|<0.2`, `|excess kurtosis|<0.5`, and Q–Q `R²>0.99`.

This is an Erdős–Kac-inspired finite-sample implication, not a test of the
number-theoretic theorem itself. Classfiles are library compilation units, not
independent end-user applications.

### Phase 4: size/cost bound and held-out incompleteness proxy

The primary callable-component population is concrete methods targeted by
exact `STATIC` or `SPECIAL` calls. Component size is Code byte length; use is
resolved invocation occurrence count. The gross savings proxy is
`max(code_length−3,0)` per use and is compared descriptively with `log2(rank)`.

The incompleteness search uses non-synthetic, exception-free methods without
branch/switch/throw/monitor/jsr/ret and 4–512 instructions. Opcode n-grams of
length 4–8 discovered in four deterministic package-hash folds must occur in at
least three training packages. Occurrences of one candidate may not overlap
within a method. Held-out net savings subtracts three bytes per
reference, one definition, and eight bytes per referencing class. Positive
held-out savings is exploratory evidence only: operands, stack contracts,
access control, semantic naming, and verifier-safe rewriting are not modeled.

### Phase 5: longitudinal component growth

Compare official OpenJDK RI 17+35 with OpenJDK EA 28+13 using the same extractor
and canonical method key. Report retained, added, removed, and net method
vocabulary; corpus bytecode and call-site growth; and JDK 28 calls from retained
method identities to added callees. Two snapshots can support finite observed
growth and adoption, but cannot establish an infinite component supply or
causal code savings.

The machine-readable result is `reuse_theorem_tests.json`; the versioned public
payload is `reuse-theorems-v1.json`.
