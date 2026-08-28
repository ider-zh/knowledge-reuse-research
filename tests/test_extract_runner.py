import hashlib

import json
import zstandard

from scripts.run_extract import module_plan_sha256, read_cached_shard_metadata, valid_cached_shard


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


def test_cached_shard_metadata_restores_audits(tmp_path) -> None:
    shard = tmp_path / "shard.jsonl.zst"
    rows = [
        {"record": "node", "name": "n"},
        {"record": "audit", "module": "Mathlib.Test", "status": "ok"},
    ]
    with shard.open("wb") as stream:
        with zstandard.ZstdCompressor().stream_writer(stream) as writer:
            for row in rows:
                writer.write((json.dumps(row) + "\n").encode())
    record_count, audits = read_cached_shard_metadata(shard)
    assert record_count == 2
    assert audits == [rows[1]]
