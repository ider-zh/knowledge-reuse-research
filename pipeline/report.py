"""Compatibility CLI for the Lean v1 report."""

from knowledge_reuse.sources.lean_mathlib.report import *  # noqa: F403
from knowledge_reuse.sources.lean_mathlib.report import main


if __name__ == "__main__":
    raise SystemExit(main())
