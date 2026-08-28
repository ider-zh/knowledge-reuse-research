# lean_mathlib_v1 handoff

- Owner: primary research agent
- Baseline commit: `6dcdf7b`
- Scope: `LeanGraph/`, Lean Python adapter, v1 configs/results
- Current gate: complete. 331/331 raw shards, 8,264/8,264 module audits,
  normalization, all ten data-quality checks, full analysis, and the standalone
  17-section/14-figure report pass.
- Verified evidence: pinned capability probe passed; golden exact 60-node and
  409-typed-edge digests pass; 1/2/4/8-worker benchmark complete; smoke
  normalize/validate/analyze/report passed.
- Intentional dirty work: direct `moduleData` declaration indexing and explicitly
  bounded expression-size metrics must be committed only after exact golden,
  adapter tests, and heavy-module timing verification.
- Generated artifacts: `vendor/`, `data/`, `results/metrics`, `results/tables`,
  and report HTML are gitignored/rebuildable.
- Formal v1 graph: 566,238 internal declarations, 24,741,186 unique typed
  edges, and 10,805 external targets. Expression-size saturation affected 7
  type metrics and 54 present value metrics; dependency edges remain complete.
- Primary result: all-declaration reuse has Gini 0.9509; the top 1% receives
  79.90% of incoming reuse edges and the top 10% receives 93.67%.
- Next safe action: freeze conclusions in the Notion experiment page, then
  coordinate any cross-source comparison through `schemas/core/` adapters.
