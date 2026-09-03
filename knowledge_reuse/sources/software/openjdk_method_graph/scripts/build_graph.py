#!/usr/bin/env python3
"""Resolve raw bytecode facts and write the OpenJDK method graph as Parquet."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import platform
import subprocess
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


csv.field_size_limit(16 * 1024 * 1024)


EXTRACTOR_VERSION = "1.1.0"
ACC_STATIC = 0x0008
ACC_BRIDGE = 0x0040
ACC_NATIVE = 0x0100
ACC_ABSTRACT = 0x0400
ACC_SYNTHETIC = 0x1000


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--jdk", type=Path, required=True)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--archive", type=Path)
    parser.add_argument("--snapshot-id", default="jdk-28+13")
    parser.add_argument("--expected-version", default="28-ea+13")
    parser.add_argument("--source-tag", default="jdk-28+13")
    parser.add_argument("--source-commit", default="6870f28fe74cbd71419bdd1d1797434366bf8114")
    parser.add_argument(
        "--binary-url",
        default="https://download.java.net/java/early_access/jdk28/13/GPL/openjdk-28-ea+13_linux-x64_bin.tar.gz",
    )
    return parser.parse_args()


def stable_id(method_key: str) -> int:
    return int.from_bytes(hashlib.sha256(method_key.encode("utf-8")).digest()[:8], "big")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_tsv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as stream:
        yield from csv.DictReader(stream, delimiter="\t")


def nullable_int(value: str) -> int | None:
    return int(value) if value else None


def method_key(module: str, class_name: str, name: str, descriptor: str) -> str:
    return f"{module}/{class_name}#{name}{descriptor}"


def write_parquet(path: Path, rows: list[dict], schema: pa.Schema) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    table = pa.Table.from_pylist(rows, schema=schema)
    pq.write_table(table, temporary, compression="zstd", use_dictionary=True)
    os.replace(temporary, path)


def main() -> int:
    args = parse_args()
    graph_id = f"software/openjdk/{args.snapshot_id}/default"
    args.output.mkdir(parents=True, exist_ok=True)
    java = args.jdk / "bin" / "java"
    if not java.is_file():
        raise SystemExit(f"missing Java executable: {java}")
    version_text = subprocess.run(
        [str(java), "-version"], capture_output=True, text=True, check=True
    ).stderr.strip()
    if args.expected_version not in version_text:
        raise SystemExit(f"unexpected JDK version:\n{version_text}")

    raw_classes = list(read_tsv(args.raw / "classes_raw.tsv"))
    raw_methods = list(read_tsv(args.raw / "methods_raw.tsv"))

    class_by_key: dict[tuple[str, str], dict] = {}
    modules_by_class: dict[str, list[str]] = defaultdict(list)
    class_rows: list[dict] = []
    for row in raw_classes:
        key = (row["module_name"], row["class_name"])
        if key in class_by_key:
            raise SystemExit(f"duplicate class key: {key}")
        class_by_key[key] = row
        modules_by_class[row["class_name"]].append(row["module_name"])
        class_rows.append({
            "module_name": row["module_name"],
            "class_name": row["class_name"],
            "super_name": row["super_name"] or None,
            "interfaces": row["interfaces"].split(",") if row["interfaces"] else [],
            "access_flags": int(row["access_flags"]),
            "source_file": row["source_file"] or None,
            "classfile_size": int(row["classfile_size"]),
            "constant_pool_entries": int(row["constant_pool_entries"]),
        })

    method_rows: list[dict] = []
    declaration_id: dict[tuple[str, str, str, str], int] = {}
    id_to_key: dict[int, str] = {}
    for row in raw_methods:
        key = method_key(row["module_name"], row["class_name"],
                         row["method_name"], row["descriptor"])
        identifier = stable_id(key)
        previous_key = id_to_key.setdefault(identifier, key)
        if previous_key != key:
            raise SystemExit(f"method ID collision: {previous_key!r} and {key!r}")
        declaration_key = (row["module_name"], row["class_name"],
                           row["method_name"], row["descriptor"])
        if declaration_key in declaration_id:
            raise SystemExit(f"duplicate method declaration: {key}")
        declaration_id[declaration_key] = identifier
        flags = int(row["access_flags"])
        method_rows.append({
            "method_id": identifier,
            "method_key": key,
            "module_name": row["module_name"],
            "package_name": row["package_name"],
            "class_name": row["class_name"],
            "method_name": row["method_name"],
            "descriptor": row["descriptor"],
            "access_flags": flags,
            "source_file": row["source_file"] or None,
            "first_line": nullable_int(row["first_line"]),
            "last_line": nullable_int(row["last_line"]),
            "is_constructor": row["method_name"] == "<init>",
            "is_static_init": row["method_name"] == "<clinit>",
            "is_static": bool(flags & ACC_STATIC),
            "is_abstract": bool(flags & ACC_ABSTRACT),
            "is_native": bool(flags & ACC_NATIVE),
            "is_synthetic": bool(flags & ACC_SYNTHETIC),
            "is_bridge": bool(flags & ACC_BRIDGE),
            "has_code": row["has_code"] == "true",
            "bytecode_length": nullable_int(row["bytecode_length"]),
            "instruction_count": nullable_int(row["instruction_count"]),
            "max_stack": nullable_int(row["max_stack"]),
            "max_locals": nullable_int(row["max_locals"]),
            "has_control_flow": row["has_control_flow"] == "true",
            "has_exception_handlers": row["has_exception_handlers"] == "true",
        })

    method_code_rows = []
    for row in read_tsv(args.raw / "method_code_raw.tsv"):
        key = method_key(row["module_name"], row["class_name"],
                         row["method_name"], row["descriptor"])
        method_code_rows.append({
            "method_id": stable_id(key),
            "bytecode_length": int(row["bytecode_length"]),
            "opcodes": row["opcodes"].split(",") if row["opcodes"] else [],
            "instruction_sizes": [int(value) for value in row["instruction_sizes"].split(",")]
            if row["instruction_sizes"] else [],
        })

    varhandle_polymorphic = {
        name: identifier
        for (module, class_name, name, descriptor), identifier in declaration_id.items()
        if module == "java.base" and class_name == "java/lang/invoke/VarHandle"
        and descriptor.startswith("([Ljava/lang/Object;)")
    }

    def candidate_modules(class_name: str, preferred_module: str) -> list[str]:
        modules = modules_by_class.get(class_name, [])
        if preferred_module in modules:
            return [preferred_module] + [m for m in modules if m != preferred_module]
        return modules

    resolution_cache: dict[tuple[str, str, str, str], tuple[int, str] | None] = {}

    def resolve(preferred_module: str, owner: str, name: str,
                descriptor: str) -> tuple[int, str] | None:
        cache_key = (preferred_module, owner, name, descriptor)
        if cache_key in resolution_cache:
            return resolution_cache[cache_key]
        if not owner:
            resolution_cache[cache_key] = None
            return None

        roots = [(module, owner) for module in candidate_modules(owner, preferred_module)]
        queue = deque((module, class_name, True) for module, class_name in roots)
        visited: set[tuple[str, str]] = set()
        while queue:
            module, class_name, exact = queue.popleft()
            class_key = (module, class_name)
            if class_key in visited:
                continue
            visited.add(class_key)
            identifier = declaration_id.get((module, class_name, name, descriptor))
            if identifier is not None:
                answer = (identifier, "EXACT" if exact else "INHERITED")
                resolution_cache[cache_key] = answer
                return answer
            metadata = class_by_key.get(class_key)
            if metadata is None:
                continue
            parents = []
            if metadata["super_name"]:
                parents.append(metadata["super_name"])
            if metadata["interfaces"]:
                parents.extend(metadata["interfaces"].split(","))
            for parent in parents:
                for parent_module in candidate_modules(parent, module):
                    queue.append((parent_module, parent, False))

        # Signature-polymorphic MethodHandle calls use the call-site descriptor.
        if owner == "java/lang/invoke/MethodHandle" and name in {"invoke", "invokeExact"}:
            canonical = "([Ljava/lang/Object;)Ljava/lang/Object;"
            identifier = declaration_id.get(("java.base", owner, name, canonical))
            if identifier is not None:
                answer = (identifier, "SIGNATURE_POLYMORPHIC")
                resolution_cache[cache_key] = answer
                return answer

        # Every VarHandle access-mode method is signature-polymorphic. Its
        # bytecode call-site descriptor is specialized, while the declaration
        # accepts Object[] and has a name-specific erased return type.
        if owner == "java/lang/invoke/VarHandle":
            identifier = varhandle_polymorphic.get(name)
            if identifier is not None:
                answer = (identifier, "SIGNATURE_POLYMORPHIC")
                resolution_cache[cache_key] = answer
                return answer

        resolution_cache[cache_key] = None
        return None

    callsite_rows: list[dict] = []
    unresolved_rows: list[dict] = []
    edge_counts: Counter[tuple[int, int, str]] = Counter()
    raw_call_count = 0
    for row in read_tsv(args.raw / "calls_raw.tsv"):
        raw_call_count += 1
        caller = declaration_id.get((row["caller_module"], row["caller_class"],
                                     row["caller_name"], row["caller_descriptor"]))
        if caller is None:
            raise SystemExit(f"missing caller declaration: {row}")
        resolved = resolve(row["caller_module"], row["declared_owner"],
                           row["declared_name"], row["declared_descriptor"])
        base = {
            "caller_method_id": caller,
            "invoke_kind": row["invoke_kind"],
            "instruction_ordinal": int(row["instruction_ordinal"]),
            "source_line": nullable_int(row["source_line"]),
            "declared_owner": row["declared_owner"],
            "declared_name": row["declared_name"],
            "declared_descriptor": row["declared_descriptor"],
            "bootstrap_owner": row["bootstrap_owner"] or None,
            "bootstrap_name": row["bootstrap_name"] or None,
        }
        if resolved is None:
            unresolved_rows.append({
                **base,
                "reason": row["resolution_hint"]
                if row["resolution_hint"] == "UNRESOLVED_DYNAMIC"
                else "TARGET_NOT_IN_CORPUS",
            })
            continue
        callee, resolution = resolved
        if row["resolution_hint"] == "BOOTSTRAP_HANDLE":
            resolution = "BOOTSTRAP_HANDLE"
        callsite_rows.append({
            **base,
            "callee_method_id": callee,
            "resolution": resolution,
        })
        edge_counts[(caller, callee, row["invoke_kind"])] += 1

    edge_rows = [
        {
            "caller_method_id": caller,
            "callee_method_id": callee,
            "invoke_kind": kind,
            "callsite_count": count,
        }
        for (caller, callee, kind), count in sorted(edge_counts.items())
    ]
    core_edge_counts: Counter[tuple[int, int]] = Counter()
    for (caller, callee, _kind), count in edge_counts.items():
        core_edge_counts[(caller, callee)] += count
    core_node_rows = [
        {
            "graph_id": graph_id,
            "node_id": row["method_id"],
            "native_id": row["method_key"],
            "label": f'{row["class_name"].replace("/", ".")}.{row["method_name"]}{row["descriptor"]}',
            "node_type": "method",
            "domain": row["module_name"],
            "is_generated": row["is_synthetic"],
            "size_source": row["bytecode_length"],
            "size_semantic": None,
        }
        for row in method_rows
    ]
    core_link_rows = [
        {
            "graph_id": graph_id,
            "src_id": caller,
            "dst_id": callee,
            "relation": "CALLS",
            "multiplicity": count,
        }
        for (caller, callee), count in sorted(core_edge_counts.items())
    ]

    method_schema = pa.schema([
        ("method_id", pa.uint64()), ("method_key", pa.string()),
        ("module_name", pa.string()), ("package_name", pa.string()),
        ("class_name", pa.string()), ("method_name", pa.string()),
        ("descriptor", pa.string()), ("access_flags", pa.int32()),
        ("source_file", pa.string()), ("first_line", pa.int32()),
        ("last_line", pa.int32()), ("is_constructor", pa.bool_()),
        ("is_static_init", pa.bool_()), ("is_static", pa.bool_()),
        ("is_abstract", pa.bool_()), ("is_native", pa.bool_()),
        ("is_synthetic", pa.bool_()), ("is_bridge", pa.bool_()),
        ("has_code", pa.bool_()), ("bytecode_length", pa.uint32()),
        ("instruction_count", pa.uint32()), ("max_stack", pa.uint16()),
        ("max_locals", pa.uint16()), ("has_control_flow", pa.bool_()),
        ("has_exception_handlers", pa.bool_()),
    ])
    class_schema = pa.schema([
        ("module_name", pa.string()), ("class_name", pa.string()),
        ("super_name", pa.string()), ("interfaces", pa.list_(pa.string())),
        ("access_flags", pa.int32()), ("source_file", pa.string()),
        ("classfile_size", pa.uint32()), ("constant_pool_entries", pa.uint16()),
    ])
    method_code_schema = pa.schema([
        ("method_id", pa.uint64()), ("bytecode_length", pa.uint32()),
        ("opcodes", pa.list_(pa.string())),
        ("instruction_sizes", pa.list_(pa.uint32())),
    ])
    callsite_schema = pa.schema([
        ("caller_method_id", pa.uint64()), ("invoke_kind", pa.string()),
        ("instruction_ordinal", pa.int32()), ("source_line", pa.int32()),
        ("declared_owner", pa.string()), ("declared_name", pa.string()),
        ("declared_descriptor", pa.string()), ("bootstrap_owner", pa.string()),
        ("bootstrap_name", pa.string()), ("callee_method_id", pa.uint64()),
        ("resolution", pa.string()),
    ])
    unresolved_schema = pa.schema([
        ("caller_method_id", pa.uint64()), ("invoke_kind", pa.string()),
        ("instruction_ordinal", pa.int32()), ("source_line", pa.int32()),
        ("declared_owner", pa.string()), ("declared_name", pa.string()),
        ("declared_descriptor", pa.string()), ("bootstrap_owner", pa.string()),
        ("bootstrap_name", pa.string()), ("reason", pa.string()),
    ])
    edge_schema = pa.schema([
        ("caller_method_id", pa.uint64()), ("callee_method_id", pa.uint64()),
        ("invoke_kind", pa.string()), ("callsite_count", pa.uint32()),
    ])
    core_node_schema = pa.schema([
        ("graph_id", pa.string()), ("node_id", pa.uint64()),
        ("native_id", pa.string()), ("label", pa.string()),
        ("node_type", pa.string()), ("domain", pa.string()),
        ("is_generated", pa.bool_()), ("size_source", pa.uint64()),
        ("size_semantic", pa.uint64()),
    ])
    core_link_schema = pa.schema([
        ("graph_id", pa.string()), ("src_id", pa.uint64()),
        ("dst_id", pa.uint64()), ("relation", pa.string()),
        ("multiplicity", pa.uint64()),
    ])

    write_parquet(args.output / "methods.parquet", method_rows, method_schema)
    write_parquet(args.output / "classes.parquet", class_rows, class_schema)
    write_parquet(args.output / "method_code.parquet", method_code_rows, method_code_schema)
    write_parquet(args.output / "call_sites.parquet", callsite_rows, callsite_schema)
    write_parquet(args.output / "unresolved_calls.parquet", unresolved_rows, unresolved_schema)
    write_parquet(args.output / "method_edges.parquet", edge_rows, edge_schema)
    write_parquet(args.output / "graph_core_nodes.parquet", core_node_rows, core_node_schema)
    write_parquet(args.output / "graph_core_links.parquet", core_link_rows, core_link_schema)

    jmods = sorted((args.jdk / "jmods").glob("*.jmod"))
    output_names = ["methods.parquet", "classes.parquet", "method_code.parquet", "call_sites.parquet",
                    "unresolved_calls.parquet", "method_edges.parquet",
                    "graph_core_nodes.parquet", "graph_core_links.parquet"]
    manifest = {
        "spec_version": "1.0",
        "extractor_version": EXTRACTOR_VERSION,
        "graph_id": graph_id,
        "source": {
            "repository": "https://github.com/openjdk/jdk",
            "tag": args.source_tag,
            "commit": args.source_commit or None,
            "binary_url": args.binary_url or None,
        },
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "jdk_version": version_text.splitlines(),
        "platform": platform.platform(),
        "input_archive": {
            "filename": args.archive.name if args.archive else None,
            "size_bytes": args.archive.stat().st_size if args.archive else None,
            "sha256": sha256_file(args.archive) if args.archive else None,
        },
        "jmods": [
            {"name": path.name, "size_bytes": path.stat().st_size,
             "sha256": sha256_file(path)} for path in jmods
        ],
        "output_datasets": [
            {"name": name, "size_bytes": (args.output / name).stat().st_size,
             "sha256": sha256_file(args.output / name)} for name in output_names
        ],
        "counts": {
            "jmods": len(jmods), "classes": len(class_rows),
            "methods": len(method_rows), "raw_invocations": raw_call_count,
            "resolved_call_sites": len(callsite_rows),
            "unresolved_call_sites": len(unresolved_rows),
            "aggregated_method_edges": len(edge_rows),
            "aggregated_callsite_sum": sum(edge_counts.values()),
            "graph_core_nodes": len(core_node_rows),
            "graph_core_links": len(core_link_rows),
            "graph_core_multiplicity_sum": sum(core_edge_counts.values()),
        },
    }
    manifest_path = args.output / "graph_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    method_ids = {row["method_id"] for row in method_rows}
    method_by_id = {row["method_id"]: row["method_key"] for row in method_rows}
    endpoint_ok = all(row["caller_method_id"] in method_ids and
                      row["callee_method_id"] in method_ids for row in callsite_rows)
    aggregate_ok = sum(row["callsite_count"] for row in edge_rows) == len(callsite_rows)
    core_ok = (len(core_node_rows) == len(method_rows)
               and sum(row["multiplicity"] for row in core_link_rows) == len(callsite_rows))
    false_body_count = sum(
        1 for row in method_rows
        if (row["is_native"] or row["is_abstract"]) and row["has_code"]
    )
    kind_counts = Counter(row["invoke_kind"] for row in callsite_rows)
    resolution_counts = Counter(row["resolution"] for row in callsite_rows)
    unresolved_reason_counts = Counter(row["reason"] for row in unresolved_rows)
    constructor_count = sum(row["is_constructor"] for row in method_rows)
    static_init_count = sum(row["is_static_init"] for row in method_rows)
    native_count = sum(row["is_native"] for row in method_rows)
    abstract_count = sum(row["is_abstract"] for row in method_rows)
    line_mapped_count = sum(row["source_line"] is not None for row in callsite_rows)
    required_kinds = {"STATIC", "SPECIAL", "VIRTUAL", "INTERFACE", "DYNAMIC"}
    kinds_ok = required_kinds.issubset(kind_counts)
    samples = {}
    for kind in sorted(required_kinds):
        sample = next(row for row in callsite_rows if row["invoke_kind"] == kind)
        samples[kind] = {
            "caller": method_by_id[sample["caller_method_id"]],
            "callee": method_by_id[sample["callee_method_id"]],
            "source_line": sample["source_line"],
        }
    overall_pass = (endpoint_ok and aggregate_ok and core_ok and false_body_count == 0
                    and kinds_ok and constructor_count > 0 and static_init_count > 0
                    and native_count > 0 and abstract_count > 0)
    report = f"""# OpenJDK {args.snapshot_id} Method Graph Validation Report

Generated: {manifest['generated_at_utc']}

## Result

{'PASS' if overall_pass else 'FAIL'}

## Corpus

- JMODs: {len(jmods):,}
- Classes: {len(class_rows):,}
- Methods: {len(method_rows):,}
- Raw invocation facts: {raw_call_count:,}
- Resolved call sites: {len(callsite_rows):,}
- Unresolved call sites: {len(unresolved_rows):,}
- Aggregated method edges: {len(edge_rows):,}

## Integrity checks

- Resolved endpoints exist: {endpoint_ok}
- Aggregated counts equal resolved call sites: {aggregate_ok}
- Graph-core projection matches native graph: {core_ok}
- Native/abstract methods incorrectly containing code: {false_body_count}
- Method ID collisions: 0
- All five invocation kinds present: {kinds_ok}
- Constructors: {constructor_count:,}
- Static initializers: {static_init_count:,}
- Native methods: {native_count:,}
- Abstract methods: {abstract_count:,}
- Resolved call sites with source lines: {line_mapped_count:,} / {len(callsite_rows):,}

## Invocation kinds

{json.dumps(dict(sorted(kind_counts.items())), indent=2)}

## Resolution modes

{json.dumps(dict(sorted(resolution_counts.items())), indent=2)}

## Unresolved reasons

{json.dumps(dict(sorted(unresolved_reason_counts.items())), indent=2)}

## Deterministic samples

{json.dumps(samples, indent=2)}

## Scope limitation

This is the exact Java bytecode-reference graph. Native implementations,
reflection assembled at runtime, and runtime virtual dispatch expansion are not
included.
"""
    (args.output / "validation_report.md").write_text(report, encoding="utf-8")
    print(json.dumps(manifest["counts"], indent=2))
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
