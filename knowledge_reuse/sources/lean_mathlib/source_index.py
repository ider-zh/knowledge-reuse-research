"""Declaration-range source metrics for the Lean adapter."""

from __future__ import annotations

import pathlib
import re
from functools import lru_cache

import polars as pl


TOKEN_PATTERN = re.compile(r"[A-Za-z_][A-Za-z0-9_']*|\d+|[^\s]", re.UNICODE)


@lru_cache(maxsize=512)
def source_lines(path: pathlib.Path) -> tuple[str, ...]:
    return tuple(path.read_text(errors="replace").splitlines(keepends=True))


def slice_range(
    path: pathlib.Path,
    start_line: int | None,
    start_column: int | None,
    end_line: int | None,
    end_column: int | None,
) -> str | None:
    if None in (start_line, start_column, end_line, end_column):
        return None
    assert start_line is not None
    assert start_column is not None
    assert end_line is not None
    assert end_column is not None
    lines = source_lines(path)
    if start_line < 1 or end_line < start_line or end_line > len(lines):
        return None
    selected = list(lines[start_line - 1 : end_line])
    if not selected:
        return None
    selected[0] = selected[0][start_column:]
    if len(selected) == 1:
        selected[0] = selected[0][: max(0, end_column - start_column)]
    else:
        selected[-1] = selected[-1][:end_column]
    return "".join(selected)


def add_source_metrics(nodes: pl.DataFrame, checkout: pathlib.Path) -> pl.DataFrame:
    rows = []
    for row in nodes.iter_rows(named=True):
        source_file = row["source_file"]
        text = (
            slice_range(
                checkout / source_file,
                row["source_start_line"],
                row["source_start_column"],
                row["source_end_line"],
                row["source_end_column"],
            )
            if source_file
            else None
        )
        rows.append(
            {
                "name": row["name"],
                "source_bytes": len(text.encode()) if text is not None else None,
                "source_lines": text.count("\n") + 1 if text is not None else None,
                "source_tokens": len(TOKEN_PATTERN.findall(text)) if text is not None else None,
            }
        )
    metrics = pl.DataFrame(
        rows,
        schema={
            "name": pl.String,
            "source_bytes": pl.UInt64,
            "source_lines": pl.UInt32,
            "source_tokens": pl.UInt32,
        },
    )
    return nodes.join(metrics, on="name", how="left", validate="1:1")
