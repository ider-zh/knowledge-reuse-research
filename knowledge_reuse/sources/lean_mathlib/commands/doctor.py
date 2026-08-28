from __future__ import annotations

import json
import pathlib
import shutil
import sys


REQUIRED = ("git", "uv", "just")
OPTIONAL = ("lean", "lake", "zstd", "duckdb", "rustc")


def locate(name: str) -> str | None:
    found = shutil.which(name)
    elan = pathlib.Path.home() / ".elan" / "bin" / name
    return found or (str(elan) if elan.is_file() else None)


def main() -> int:
    tools = {name: locate(name) for name in (*REQUIRED, *OPTIONAL)}
    payload = {
        "python": sys.version.split()[0],
        "tools": tools,
        "missing_required": [name for name in REQUIRED if tools[name] is None],
        "missing_optional": [name for name in OPTIONAL if tools[name] is None],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if payload["missing_required"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
