# Repository instructions

@/home/ider/.codex/RTK.md

Follow the linked Notion experiment specification. In particular:

- validate pinned Lean APIs with fixtures before implementing at scale;
- keep version-sensitive Lean APIs inside `LeanGraph/Compat.lean`;
- never silently treat unavailable proof bodies or failed modules as empty;
- do not run full extraction before capability and golden gates pass;
- keep raw data immutable and make every derived artifact rebuildable;
- make a small verified commit after each independent phase.

## Multi-agent workstreams

Read `docs/architecture.md` before adding a source or experiment. Work within
one owned boundary unless a shared-core change is explicitly coordinated:

- Lean/mathlib: `LeanGraph/`, `knowledge_reuse/sources/lean_mathlib/`, and
  `experiments/lean_mathlib_v1/`;
- Wikipedia: `knowledge_reuse/sources/wikipedia/` and
  `experiments/wikipedia_v1/`;
- software: `knowledge_reuse/sources/software/` and
  `experiments/software_v1/`;
- shared: `knowledge_reuse/analysis/` and `schemas/core/`.

Each source directory has local `AGENTS.md` rules. Keep a handoff under
`docs/handoffs/` while a workstream is active. Never stage, rewrite, or commit
another agent's dirty files. Shared-contract changes require adapter tests and
explicit migration notes. Use source/snapshot namespaced data and experiment
namespaced results for all new work; Lean v1 paths remain frozen until its
formal report is complete.
