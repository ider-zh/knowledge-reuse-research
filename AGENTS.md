# Repository instructions

@/home/ider/.codex/RTK.md

Follow the linked Notion experiment specification. In particular:

- validate pinned Lean APIs with fixtures before implementing at scale;
- keep version-sensitive Lean APIs inside
  `knowledge_reuse/sources/lean_mathlib/lean/LeanGraph/Compat.lean`;
- never silently treat unavailable proof bodies or failed modules as empty;
- do not run full extraction before capability and golden gates pass;
- keep raw data immutable and make every derived artifact rebuildable;
- make a small verified commit after each independent phase.

## Multi-agent workstreams

Read `docs/architecture.md` before adding a source or experiment. Work within
one owned boundary unless a shared-core change is explicitly coordinated:

- Lean/mathlib: `knowledge_reuse/sources/lean_mathlib/` and
  `experiments/lean_mathlib_v1/`;
- Wikipedia: `knowledge_reuse/sources/wikipedia/` and
  `experiments/wikipedia_v1/`;
- software: `knowledge_reuse/sources/software/` and
  `experiments/software_v1/`;
- shared: `knowledge_reuse/analysis/` and `schemas/core/`.

Each source directory has local `AGENTS.md` rules. Keep a handoff under
`docs/handoffs/` while a workstream is active. Never stage, rewrite, or commit
another agent's dirty files. Shared-contract changes require adapter tests and
explicit migration notes. All sources use source/snapshot namespaced data and
experiment-namespaced results; do not introduce unscoped files under `data/`
or `results/`.

## Research report and website writing

Write every reader-facing report and research website as a formal research
report or senior engineering document, not as a developer execution log.

- Write for the final reader. Present the research question, concepts,
  methods, evidence, findings, limitations, and implications; do not narrate
  the agent's work process.
- Prefer evidence that helps the reader answer: what was found, what supports
  it, and what it means. Do not use the page to prove that a task was completed.
- Remove operational details that have no research value, including processed
  task or module counts, `failed`/`partial` counters, pipeline status, progress
  messages, internal field names such as `completeness.configured_corpus`, and
  statements such as “checked”, “completed”, or “successfully extracted”.
- Include corpus scope or data-quality limitations only when they affect the
  interpretation, validity, or reproducibility of a result. Express them in
  reader-facing methodological language rather than pipeline terminology.
- Apply a concision-first rule: delete any content that can be removed without
  weakening the reader's understanding of the argument, evidence, method, or
  limitations.
- Keep implementation and operational tracking in developer documentation,
  handoffs, manifests, or logs rather than in the research narrative.
