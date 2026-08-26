# Repository instructions

@/home/ider/.codex/RTK.md

Follow the linked Notion experiment specification. In particular:

- validate pinned Lean APIs with fixtures before implementing at scale;
- keep version-sensitive Lean APIs inside `LeanGraph/Compat.lean`;
- never silently treat unavailable proof bodies or failed modules as empty;
- do not run full extraction before capability and golden gates pass;
- keep raw data immutable and make every derived artifact rebuildable;
- make a small verified commit after each independent phase.

