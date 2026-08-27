# Graph core schema v1

This is the portable projection used by cross-system reuse analysis. Adapters
may retain additional source-native columns in canonical Parquet tables.

## Nodes

| Column | Type | Meaning |
| --- | --- | --- |
| graph_id | string | Stable graph/snapshot identifier |
| node_id | uint64 | Deterministic ID within graph_id |
| native_id | string | Lossless source-native identifier |
| label | string | Human-readable name |
| node_type | string | Declaration, page, function, package, etc. |
| domain | string? | Reproducible source-local taxonomy |
| is_generated | bool? | Transparent adapter classification |
| size_source | uint64? | Source size with unit metadata |
| size_semantic | uint64? | Native semantic/AST size |

## Links

| Column | Type | Meaning |
| --- | --- | --- |
| graph_id | string | Stable graph/snapshot identifier |
| src_id | uint64 | Consumer/source node |
| dst_id | uint64 | Dependency/target node |
| relation | string | Stable source-native relation label |
| multiplicity | uint64? | Repeated occurrences when meaningful |

Direction is always consumer/source → dependency/target, so reuse is target
indegree from unique source nodes. External targets require an external-node
table or explicit audit reason.

Each graph also publishes expected/extracted unit counts, failures, duplicate
and dangling counts, null statistics, sample checksums, config hashes, and
source-version metadata.
