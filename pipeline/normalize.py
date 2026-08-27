"""Compatibility CLI for Lean v1 normalization."""

from knowledge_reuse.sources.lean_mathlib.normalize import *  # noqa: F403
from knowledge_reuse.sources.lean_mathlib.normalize import main


if __name__ == "__main__":
    raise SystemExit(main())
