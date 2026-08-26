from __future__ import annotations

import argparse
import hashlib
import json
import pathlib


ROOT = pathlib.Path(__file__).resolve().parents[1]
INVENTORY = ROOT / "results" / "inventory.json"
PLAN = ROOT / "results" / "shard-plan.json"


def make_plan(shard_size: int) -> dict[str, object]:
    inventory = json.loads(INVENTORY.read_text())
    modules = sorted(
        entry["module"] for entry in inventory["modules"] if entry["status"] == "included"
    )
    shards = []
    for index, start in enumerate(range(0, len(modules), shard_size)):
        members = modules[start : start + shard_size]
        digest = hashlib.sha256(("\n".join(members) + "\n").encode()).hexdigest()
        shards.append({"id": f"shard-{index:05d}", "modules": members, "sha256": digest})
    return {
        "schema_version": "shard-plan-v1",
        "snapshot_id": inventory["snapshot_id"],
        "module_count": len(modules),
        "shard_size": shard_size,
        "shard_count": len(shards),
        "shards": shards,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shard-size", type=int, default=25)
    args = parser.parse_args()
    if args.shard_size < 1:
        parser.error("--shard-size must be positive")
    plan = make_plan(args.shard_size)
    PLAN.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: plan[key] for key in ("module_count", "shard_count", "shard_size")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

