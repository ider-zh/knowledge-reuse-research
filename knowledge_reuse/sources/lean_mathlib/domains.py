"""Lean/mathlib module identity and repository-domain taxonomy."""

from __future__ import annotations

import pathlib


def module_from_path(path: pathlib.Path) -> str:
    return ".".join(path.with_suffix("").parts)


def domain_from_module(module: str) -> str:
    parts = module.split(".")
    return parts[1] if len(parts) > 1 and parts[0] == "Mathlib" else parts[0]
