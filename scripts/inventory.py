from __future__ import annotations

import fnmatch
import hashlib
import json
import pathlib
import tomllib
from typing import Any

from knowledge_reuse.sources.lean_mathlib.domains import domain_from_module, module_from_path


ROOT = pathlib.Path(__file__).resolve().parents[1]
MATHLIB = ROOT / "vendor" / "mathlib4"
RESULT = ROOT / "results" / "inventory.json"


def sha256_lines(values: list[str]) -> str:
    return hashlib.sha256(("\n".join(values) + "\n").encode()).hexdigest()


def load_exclusion_rules() -> list[dict[str, str]]:
    config = tomllib.loads((ROOT / "configs" / "exclusions.toml").read_text())
    return config["rule"]


def exclusion_for(path: str, rules: list[dict[str, str]]) -> dict[str, str] | None:
    candidates = (path, path.removeprefix("Mathlib/"))
    return next(
        (
            rule
            for rule in rules
            if any(fnmatch.fnmatch(candidate, rule["pattern"]) for candidate in candidates)
        ),
        None,
    )


def inspect_source(path: pathlib.Path) -> dict[str, int]:
    text = path.read_text(errors="replace")
    return {
        "bytes": path.stat().st_size,
        "lines": text.count("\n") + 1,
        "theorem_like": text.count("theorem ") + text.count("lemma "),
        "structure_like": text.count("structure ") + text.count("class "),
        "instance_like": text.count("instance "),
    }


def recommend_smoke(entries: list[dict[str, Any]]) -> list[str]:
    included = [entry for entry in entries if entry["status"] == "included"]
    selected: list[str] = []
    for domain in ("Algebra", "Analysis", "Topology", "NumberTheory", "CategoryTheory"):
        candidates = [
            entry
            for entry in included
            if entry["domain"] == domain and 2_000 <= entry["bytes"] <= 30_000
        ]
        if candidates:
            candidates.sort(key=lambda entry: (entry["bytes"], entry["module"]))
            selected.append(candidates[0]["module"])
    bounded = [entry for entry in included if entry["bytes"] <= 60_000]
    if bounded:
        structure = max(
            bounded,
            key=lambda entry: (
                entry["structure_like"] + entry["instance_like"],
                -entry["bytes"],
                entry["module"],
            ),
        )
        proof = max(
            bounded,
            key=lambda entry: (entry["theorem_like"], -entry["bytes"], entry["module"]),
        )
        selected.extend((structure["module"], proof["module"]))
    return sorted(set(selected))


def build_inventory() -> dict[str, Any]:
    if not MATHLIB.is_dir():
        raise SystemExit("missing vendor/mathlib4; run bootstrap first")
    rules = load_exclusion_rules()
    entries: list[dict[str, Any]] = []
    for absolute in sorted((MATHLIB / "Mathlib").rglob("*.lean")):
        relative = absolute.relative_to(MATHLIB)
        relative_string = relative.as_posix()
        rule = exclusion_for(relative_string, rules)
        source = inspect_source(absolute)
        entries.append(
            {
                "module": module_from_path(relative),
                "source_file": relative_string,
                "domain": domain_from_module(module_from_path(relative)),
                "status": "excluded" if rule else "included",
                "exclusion_pattern": rule["pattern"] if rule else None,
                "exclusion_reason": rule["reason"] if rule else None,
                **source,
            }
        )
    included = [entry["module"] for entry in entries if entry["status"] == "included"]
    excluded = [entry["module"] for entry in entries if entry["status"] == "excluded"]
    return {
        "schema_version": "module-inventory-v1",
        "snapshot_id": "mathlib-v4.32.1",
        "mathlib_commit": "520045ab14e26149ee970e2e617ca04b09bde5d6",
        "corpus_glob": "Mathlib/**/*.lean",
        "exclusion_rules": rules,
        "summary": {
            "discovered": len(entries),
            "included": len(included),
            "excluded": len(excluded),
            "included_modules_sha256": sha256_lines(included),
            "excluded_modules_sha256": sha256_lines(excluded),
        },
        "recommended_smoke_modules": recommend_smoke(entries),
        "modules": entries,
    }


def main() -> int:
    inventory = build_inventory()
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n")
    print(json.dumps(inventory["summary"], indent=2, sort_keys=True))
    print("recommended smoke modules:")
    print("\n".join(inventory["recommended_smoke_modules"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
