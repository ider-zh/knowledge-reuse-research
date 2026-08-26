from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import tomllib


ROOT = pathlib.Path(__file__).resolve().parents[1]
LOCK = ROOT / "versions.lock.toml"
CHECKOUT = ROOT / "vendor" / "mathlib4"
MANIFEST = ROOT / "results" / "bootstrap-manifest.json"


def run(*args: str, cwd: pathlib.Path = ROOT) -> str:
    return subprocess.run(args, cwd=cwd, check=True, text=True, capture_output=True).stdout.strip()


def main() -> int:
    config = tomllib.loads(LOCK.read_text())
    repo = config["mathlib"]["repository"]
    tag = config["mathlib"]["tag"]

    if not CHECKOUT.exists():
        CHECKOUT.parent.mkdir(parents=True, exist_ok=True)
        run("git", "clone", "--filter=blob:none", "--no-checkout", repo, str(CHECKOUT))

    run("git", "fetch", "--tags", "--force", "origin", cwd=CHECKOUT)
    run("git", "checkout", "--detach", tag, cwd=CHECKOUT)
    commit = run("git", "rev-parse", "HEAD", cwd=CHECKOUT)
    dirty = run("git", "status", "--porcelain", cwd=CHECKOUT)
    toolchain = (CHECKOUT / "lean-toolchain").read_text().strip()

    expected = config["mathlib"]["commit"]
    if expected != "UNRESOLVED" and commit != expected:
        raise SystemExit(f"mathlib commit mismatch: expected {expected}, got {commit}")
    if dirty:
        raise SystemExit("mathlib checkout is dirty")

    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": config["schema_version"],
        "mathlib_repository": repo,
        "mathlib_tag": tag,
        "mathlib_commit": commit,
        "lean_toolchain": toolchain,
        "checkout_clean": True,
        "git_path": shutil.which("git"),
    }
    MANIFEST.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

