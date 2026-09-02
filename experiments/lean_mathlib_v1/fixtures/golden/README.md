# Golden semantic fixture

`LeanGraph.ProbeFixture` deliberately covers the required hand-authored
theorem/definition/type/body relationships plus generated declarations from an
inductive, structure, class, instance, namespace, and private theorem.

The golden test compares the exact node-name set, exact `(src, dst, edge_type)`
set, and exact `(src, dst, edge_type, multiplicity)` weighted set using
canonical JSON SHA-256 digests. Counts and several human-auditable semantic
edges are asserted separately so a digest change cannot be accepted without
reviewing the intended relationships. In particular, `T1 : P → P` must retain
two TYPE occurrences of `P`. Updating the pinned Lean toolchain requires
reviewing and updating all expectations.

Golden v3 also pins all four Type/Value expression complexity levels: unique
pointer nodes, DAG arcs, maximum depth, and expanded tree occurrences. The
expanded-tree values must exactly match the legacy graph fields, preventing the
sidecar from silently changing existing graph semantics.
