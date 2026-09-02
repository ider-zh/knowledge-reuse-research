# Lean edge occurrence multiplicity

`lean-graph-v2` extends each unique typed dependency edge with a required,
positive `multiplicity`. The value is the number of occurrences of the target
constant in the source declaration's elaborated TYPE or VALUE expression after
expanding Expr DAG sharing conceptually.

## Representation

The canonical table retains one row per
`(snapshot, src, dst, edge_type)`. Repeated references are represented by the
integer weight instead of physically repeating rows. Consequently, both views
remain derivable without ambiguity:

- reuse breadth: number of distinct source declarations for a target;
- reference intensity: sum of edge multiplicities for a target.

Multiplicity does not represent runtime calls, transitive dependencies, or the
number of importing modules.

## Algorithm

For each elaborated Expr, the extractor first collects pointer-distinct DAG
nodes in postorder. A second pass processes parents before children and
propagates each node's root-to-node path count. A constant node contributes its
path count to that constant's total. This restores repeated use sites while
visiting each unique Expr node and child arc once; arbitrary-precision `Nat`
prevents saturation during extraction.

The depth-80 shared-DAG fixture has 81 pointer-distinct nodes and
`1,208,925,819,614,629,174,706,176` occurrences of `Nat`. It establishes that
the cache avoids recursive expansion without discarding multiplicity.

## Compatibility and storage

The previous `lean-graph-v1` raw corpus remains unchanged under the legacy
unversioned raw and normalized directories. New extraction and normalization
write to:

```text
data/lean_mathlib/<snapshot>/raw/lean-graph-v2/<run>/
data/lean_mathlib/<snapshot>/normalized/lean-graph-v2/<run>/
```

The v2 normalizer rejects null, zero, and negative multiplicities. Identical
typed-edge records emitted for the same generated declaration in multiple
import environments collapse to one canonical row without summing their
weights; duplicate keys with conflicting multiplicities are rejected as an
identity ambiguity. This prevents both a silent fallback to the old
unique-only semantics and artificial multiplication of occurrences. Existing
v1 results remain historical evidence and must not be presented as v2
occurrence-weighted results.
