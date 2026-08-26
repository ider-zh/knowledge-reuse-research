from __future__ import annotations

import datetime as dt
import json
import pathlib
import re
import shutil
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[1]
RESULT_JSON = ROOT / "results" / "capability-probe.json"
RESULT_MD = ROOT / "results" / "capability-probe.md"
LAKE = shutil.which("lake") or str(pathlib.Path.home() / ".elan" / "bin" / "lake")


def run(*args: str) -> str:
    proc = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    output = proc.stdout + proc.stderr
    if proc.returncode:
        raise SystemExit(output)
    return output


def main() -> int:
    run(LAKE, "build", "LeanGraph.Compat", "LeanGraph.ProbeFixture")
    normal = run(LAKE, "env", "lean", "LeanGraph/ProbeNormal.lean")
    import_all = run(LAKE, "env", "lean", "LeanGraph/ProbeAll.lean")

    count_match = re.search(r"PROBE_ALL_DECLS count=(\d+)", import_all)
    checks = {
        "environment_enumeration": bool(count_match and int(count_match.group(1)) >= 10),
        "declaration_kinds": all(
            item in import_all
            for item in (
                "D2 kind=definition",
                "T2 kind=theorem",
                "Tiny kind=inductive",
                "Tiny.zero kind=constructor",
                "O1 kind=opaque",
            )
        ),
        "type_constant_references": "T2 kind=theorem" in import_all
        and "typeConsts=[LeanGraph.ProbeFixture.P]" in import_all,
        "value_constant_references": "LeanGraph.ProbeFixture.T1" in import_all,
        "module_provenance": "module=some (LeanGraph.ProbeFixture)" in normal,
        "ordinary_import_hides_values": "T2 kind=axiom" in normal and "hasValue=false" in normal,
        "import_all_exposes_values": "T2 kind=theorem" in import_all
        and "hasValue=true" in import_all,
        "import_all_supported": "PROBE_ALL_DECLS" in import_all,
        "source_ranges_imported": "hasRange=true" in import_all,
    }
    required = {key: value for key, value in checks.items() if key != "source_ranges_imported"}
    passed = all(required.values())
    payload = {
        "schema_version": "capability-probe-v1",
        "recorded_at": dt.datetime.now(dt.UTC).isoformat(),
        "mathlib_tag": "v4.32.1",
        "mathlib_commit": "520045ab14e26149ee970e2e617ca04b09bde5d6",
        "lean_toolchain": "leanprover/lean4:v4.32.1",
        "passed": passed,
        "checks": checks,
        "source_range_decision": (
            "Use semantic declaration ranges"
            if checks["source_ranges_imported"]
            else "Use a declaration-identity-preserving source indexer; imported ranges are unavailable"
        ),
        "evidence": {"ordinary_import": normal.splitlines(), "import_all": import_all.splitlines()},
    }
    RESULT_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULT_JSON.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")

    rows = "\n".join(
        f"| `{name}` | {'PASS' if value else 'OBSERVED UNAVAILABLE'} |"
        for name, value in checks.items()
    )
    RESULT_MD.write_text(
        "# Lean v4.32.1 capability probe\n\n"
        f"Overall gate: **{'PASS' if passed else 'FAIL'}**\n\n"
        "| Capability | Result |\n|---|---|\n"
        f"{rows}\n\n"
        "The source-range check is observational rather than gate-failing: the specification permits "
        "a declaration-identity-preserving source indexer when imported semantic range metadata is "
        "unavailable. Ordinary imports intentionally hide values/proofs; `import all` exposes them and "
        "preserves definition/theorem/opaque kinds in this pinned toolchain.\n"
    )
    print(json.dumps({"passed": passed, "checks": checks}, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
