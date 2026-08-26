from __future__ import annotations

import json
import shutil
import sys


REQUIRED = ("git", "uv")
OPTIONAL = ("just", "lean", "lake", "zstd", "duckdb", "rustc")


def main() -> int:
    tools = {name: shutil.which(name) for name in (*REQUIRED, *OPTIONAL)}
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

