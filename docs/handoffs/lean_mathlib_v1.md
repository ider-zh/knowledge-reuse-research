# lean_mathlib_v1 handoff

- Owner: primary research agent
- Baseline commit: `6dcdf7b`
- Scope: `knowledge_reuse/sources/lean_mathlib/`,
  `experiments/lean_mathlib_v1/`, `schemas/lean_mathlib/`, and
  `results/lean_mathlib_v1/`
- Current graph schema: `lean-graph-v2` has passed fixture and smoke validation.
  The prior full `lean-graph-v1` corpus remains immutable historical evidence;
  no v2 full extraction has been run.
- Verified v2 evidence: pinned capability probe passed; golden exact 60-node,
  409-typed-edge, and weighted-edge digests pass; the seven-module smoke graph
  passes extraction, normalization, determinism, data-quality, analysis, and
  report generation. Its 17,561 unique typed edges retain 130,517 constant
  occurrences.
- Historical v1 evidence: the 1/2/4/8-worker benchmark and full run remain
  available under the legacy data layout.
- Current migration: Lean code, commands, configuration, fixtures, schema,
  tests, data, and results now use source/experiment namespaces. See
  `docs/migrations/2026-08-28-lean-source-namespace.md`.
- Generated artifacts: `vendor/`, `data/`, experiment metrics/tables, and
  report HTML are gitignored/rebuildable.
- Formal v1 graph: 566,238 internal declarations, 24,741,186 unique typed
  edges, and 10,805 external targets. All 566,238 type-size observations and
  all 553,123 value-size observations for declarations with bodies are exact;
  no saturation or algorithmic nulls remain.
- Primary result: all-declaration reuse has Gini 0.9509; the top 1% receives
  79.90% of incoming reuse edges and the top 10% receives 93.67%.
- Migration: v2 retains exact Expr constant occurrence multiplicity as an edge
  weight while preserving unique-consumer reuse breadth as a derived view. See
  `docs/migrations/2026-09-02-lean-edge-multiplicity.md`.
- Next safe action: require capability, golden, and smoke gates before planning
  the versioned v2 full extraction. Do not overwrite or relabel v1 results.
