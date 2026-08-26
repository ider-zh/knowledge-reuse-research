from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
from typing import Any


ROOT = pathlib.Path(__file__).resolve().parents[1]
EXPECTED_PATH = ROOT / "fixtures" / "golden" / "expected.json"
RESULT_PATH = ROOT / "results" / "golden-test.json"
LAKE = shutil.which("lake") or str(pathlib.Path.home() / ".elan" / "bin" / "lake")


def canonical_sha256(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    return hashlib.sha256(data).hexdigest()


def check_golden() -> dict[str, Any]:
    expected = json.loads(EXPECTED_PATH.read_text())
    subprocess.run(
        [LAKE, "build", "lean-graph-extract", "LeanGraph.ProbeFixture"],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    proc = subprocess.run(
        [
            LAKE,
            "env",
            ".lake/build/bin/lean-graph-extract",
            expected["schema_version"],
            expected["module"],
        ],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    rows = [json.loads(line) for line in proc.stdout.splitlines()]
    nodes = sorted(row["name"] for row in rows if row["record"] == "node")
    edges = sorted(
        (row["src"], row["dst"], row["edge_type"])
        for row in rows
        if row["record"] == "edge"
    )
    audits = [row for row in rows if row["record"] == "audit"]
    node_set = set(nodes)
    edge_set = set(edges)
    checks = {
        "one_successful_audit": len(audits) == 1 and audits[0]["status"] == "ok",
        "node_count": len(nodes) == expected["node_count"],
        "node_set_exact": canonical_sha256(nodes) == expected["node_set_sha256"],
        "typed_edge_count": len(edges) == expected["typed_edge_count"],
        "typed_edge_set_exact": canonical_sha256(edges) == expected["typed_edge_set_sha256"],
        "required_nodes": set(expected["required_nodes"]) <= node_set,
        "required_typed_edges": {tuple(edge) for edge in expected["required_typed_edges"]}
        <= edge_set,
        "no_duplicate_nodes": len(nodes) == len(node_set),
        "no_duplicate_typed_edges": len(edges) == len(edge_set),
    }
    return {
        "schema_version": expected["schema_version"],
        "module": expected["module"],
        "passed": all(checks.values()),
        "checks": checks,
        "observed": {
            "node_count": len(nodes),
            "node_set_sha256": canonical_sha256(nodes),
            "typed_edge_count": len(edges),
            "typed_edge_set_sha256": canonical_sha256(edges),
        },
    }


def main() -> int:
    result = check_golden()
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

