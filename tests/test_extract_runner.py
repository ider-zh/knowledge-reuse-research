import hashlib

import json

from scripts.run_extract import module_plan_sha256, valid_cached_shard


def test_cached_shard_requires_matching_checksum(tmp_path) -> None:
    shard = tmp_path / "shard.jsonl.zst"
    shard.write_bytes(b"content")
    checksum = hashlib.sha256(b"content").hexdigest()
    plan = module_plan_sha256(["Mathlib.Test"])
    shard.with_suffix(".zst.sha256").write_text(
        json.dumps({"sha256": checksum, "module_plan_sha256": plan})
    )
    assert valid_cached_shard(shard, plan) == checksum
    assert valid_cached_shard(shard, module_plan_sha256(["Mathlib.Other"])) is None
    shard.write_bytes(b"changed")
    assert valid_cached_shard(shard, plan) is None
