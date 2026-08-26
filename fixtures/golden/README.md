# Golden semantic fixture

`LeanGraph.ProbeFixture` deliberately covers the required hand-authored
theorem/definition/type/body relationships plus generated declarations from an
inductive, structure, class, instance, namespace, and private theorem.

The golden test compares the exact node-name set and exact `(src, dst,
edge_type)` set using canonical JSON SHA-256 digests. Counts and several
human-auditable semantic edges are asserted separately so a digest change
cannot be accepted without reviewing the intended relationships. Updating the
pinned Lean toolchain requires reviewing and updating all expectations.

