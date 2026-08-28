# lean_mathlib_v1 handoff

- Owner: primary research agent
- Baseline commit: `6dcdf7b`
- Scope: `knowledge_reuse/sources/lean_mathlib/`,
  `experiments/lean_mathlib_v1/`, `schemas/lean_mathlib/`, and
  `results/lean_mathlib_v1/`
- Current gate: complete. 331/331 raw shards, 8,264/8,264 module audits,
  normalization, all ten data-quality checks, full analysis, and the standalone
  17-section/14-figure report pass.
- Verified evidence: pinned capability probe passed; golden exact 60-node and
  409-typed-edge digests pass; 1/2/4/8-worker benchmark complete; smoke
  normalize/validate/analyze/report passed.
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
- Next safe action: freeze conclusions in the Notion experiment page, then
  coordinate any cross-source comparison through `schemas/core/` adapters.
