"""Compatibility CLI for Lean v1 analysis."""

from knowledge_reuse.sources.lean_mathlib.metrics import *  # noqa: F403
from knowledge_reuse.sources.lean_mathlib.metrics import main


if __name__ == "__main__":
    raise SystemExit(main())
