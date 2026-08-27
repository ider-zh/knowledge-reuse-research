# lean_mathlib_v1 handoff

- Owner: primary research agent
- Baseline commit: `6dcdf7b`
- Scope: `LeanGraph/`, Lean Python adapter, v1 configs/results
- Current gate: 329/331 raw shards are checksum-complete; two profiled heavy
  shards remain (`shard-00113`, `shard-00151`).
- Verified evidence: pinned capability probe passed; golden exact 60-node and
  409-typed-edge digests pass; 1/2/4/8-worker benchmark complete; smoke
  normalize/validate/analyze/report passed.
- Intentional dirty work: linear-time extraction fixes in `LeanGraph/` must be
  committed only after exact golden and heavy-module timing verification.
- Generated artifacts: `vendor/`, `data/`, `results/metrics`, `results/tables`,
  and report HTML are gitignored/rebuildable.
- Next safe action: finish the extraction performance regression, resume the
  two missing shards, then normalize, validate, analyze, and report full v1.
