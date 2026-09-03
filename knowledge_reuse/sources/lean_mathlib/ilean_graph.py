"""Build a declaration graph from Lean's resolved `.ilean` source usages."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import tempfile
import tomllib
from dataclasses import asdict, dataclass
from typing import Any, Iterable

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq

from knowledge_reuse.sources.lean_mathlib.layout import (
    CONFIG_PATH,
    GRAPH_SCHEMA_VERSION,
    RESULTS_ROOT,
    ROOT,
    SOURCE_GRAPH_SCHEMA_VERSION,
    SOURCE_USAGE_SCHEMA_VERSION,
    normalized_root,
    run_results_root,
    source_graph_normalized_root,
    source_graph_raw_root,
)


CONFIG = tomllib.loads(CONFIG_PATH.read_text())
INVENTORY_PATH = RESULTS_ROOT / "inventory.json"
ILEAN_ROOT = ROOT / "vendor" / "mathlib4" / ".lake" / "build" / "lib" / "lean"
USAGE_KEY = [
    "snapshot_id",
    "module",
    "parent_decl",
    "target_module",
    "target_decl",
    "start_line",
    "start_character",
    "end_line",
    "end_character",
]
USAGE_SCHEMA = pa.schema(
    [
        pa.field("snapshot_id", pa.string(), nullable=False),
        pa.field("module", pa.string(), nullable=False),
        pa.field("parent_decl", pa.string(), nullable=True),
        pa.field("target_module", pa.string(), nullable=False),
        pa.field("target_decl", pa.string(), nullable=False),
        pa.field("start_line", pa.uint32(), nullable=False),
        pa.field("start_character", pa.uint32(), nullable=False),
        pa.field("end_line", pa.uint32(), nullable=False),
        pa.field("end_character", pa.uint32(), nullable=False),
    ]
)


@dataclass(frozen=True, order=True)
class SourceUsage:
    snapshot_id: str
    module: str
    parent_decl: str | None
    target_module: str
    target_decl: str
    start_line: int
    start_character: int
    end_line: int
    end_character: int


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def constant_identity(encoded: str) -> tuple[str, str] | None:
    """Decode the compact constant identity used as an `.ilean` reference key."""

    value = json.loads(encoded)
    if not isinstance(value, dict):
        raise ValueError(f"invalid .ilean reference identity: {encoded}")
    constant = value.get("c")
    if not isinstance(constant, dict):
        return None
    module = constant.get("m")
    name = constant.get("n")
    if not isinstance(module, str) or not isinstance(name, str):
        raise ValueError(f"invalid .ilean constant identity: {encoded}")
    return module, name


def parse_ilean(path: pathlib.Path, snapshot: str, expected_module: str) -> list[SourceUsage]:
    """Read deterministic, range-distinct global usages from one `.ilean` file."""

    payload = json.loads(path.read_text())
    module = payload.get("module")
    if module != expected_module:
        raise ValueError(f".ilean module mismatch: expected {expected_module}, observed {module}")
    observed: set[SourceUsage] = set()
    references = payload.get("references")
    if not isinstance(references, dict):
        raise ValueError(f".ilean references are unavailable: {path}")
    for encoded, reference in references.items():
        identity = constant_identity(encoded)
        if identity is None:
            continue
        target_module, target_decl = identity
        usages = reference.get("usages")
        if not isinstance(usages, list):
            raise ValueError(f".ilean usages are unavailable for {target_decl}: {path}")
        for location in usages:
            if not isinstance(location, list) or len(location) not in {4, 5}:
                raise ValueError(f"invalid .ilean usage location for {target_decl}: {location}")
            start_line, start_character, end_line, end_character = location[:4]
            if not all(
                isinstance(value, int) and value >= 0
                for value in (start_line, start_character, end_line, end_character)
            ):
                raise ValueError(f"invalid .ilean source range for {target_decl}: {location}")
            parent = location[4] if len(location) == 5 and location[4] else None
            if parent is not None and not isinstance(parent, str):
                raise ValueError(f"invalid .ilean parent declaration: {location}")
            observed.add(
                SourceUsage(
                    snapshot_id=snapshot,
                    module=module,
                    parent_decl=parent,
                    target_module=target_module,
                    target_decl=target_decl,
                    start_line=start_line,
                    start_character=start_character,
                    end_line=end_line,
                    end_character=end_character,
                )
            )
    return sorted(
        observed,
        key=lambda usage: (
            usage.snapshot_id,
            usage.module,
            usage.parent_decl or "",
            usage.target_module,
            usage.target_decl,
            usage.start_line,
            usage.start_character,
            usage.end_line,
            usage.end_character,
        ),
    )


def selected_modules(run_kind: str) -> list[dict[str, Any]]:
    inventory = json.loads(INVENTORY_PATH.read_text())["modules"]
    included = {row["module"]: row for row in inventory if row["status"] == "included"}
    if run_kind == "smoke":
        names = CONFIG["smoke"]["modules"]
        missing = sorted(set(names) - set(included))
        if missing:
            raise ValueError(f"smoke modules are absent from included inventory: {missing}")
        return [included[name] for name in sorted(names)]
    if run_kind != "full":
        raise ValueError(f"unsupported run kind: {run_kind}")
    return [included[name] for name in sorted(included)]


def ilean_path(module: str) -> pathlib.Path:
    return ILEAN_ROOT.joinpath(*module.split(".")).with_suffix(".ilean")


def write_usage_batch(writer: pq.ParquetWriter, rows: Iterable[SourceUsage]) -> int:
    values = list(rows)
    if not values:
        return 0
    columns = {field.name: [] for field in USAGE_SCHEMA}
    for row in values:
        record = asdict(row)
        for name in columns:
            columns[name].append(record[name])
    writer.write_table(pa.Table.from_pydict(columns, schema=USAGE_SCHEMA))
    return len(values)


def install_immutable(temp_path: pathlib.Path, target_path: pathlib.Path) -> str:
    observed = sha256(temp_path)
    if target_path.exists():
        if sha256(target_path) != observed:
            raise ValueError(f"immutable source-graph artifact changed: {target_path}")
        temp_path.unlink()
    else:
        temp_path.replace(target_path)
    return observed


def extract_usages(run_kind: str) -> dict[str, Any]:
    snapshot = CONFIG["snapshot_id"]
    output_dir = source_graph_raw_root(snapshot, run_kind)
    output_dir.mkdir(parents=True, exist_ok=True)
    modules = selected_modules(run_kind)
    input_digest = hashlib.sha256()
    module_rows: list[dict[str, Any]] = []
    usage_count = 0
    attributed_count = 0

    with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".parquet", delete=False) as handle:
        temp_path = pathlib.Path(handle.name)
    writer = pq.ParquetWriter(temp_path, USAGE_SCHEMA, compression="zstd", use_dictionary=True)
    try:
        for row in modules:
            module = row["module"]
            path = ilean_path(module)
            if not path.is_file():
                raise FileNotFoundError(f"missing .ilean for configured module {module}: {path}")
            content_hash = sha256(path)
            input_digest.update(f"{module}\0{content_hash}\n".encode())
            usages = parse_ilean(path, snapshot, module)
            count = write_usage_batch(writer, usages)
            attributed = sum(usage.parent_decl is not None for usage in usages)
            usage_count += count
            attributed_count += attributed
            module_rows.append(
                {
                    "snapshot_id": snapshot,
                    "module": module,
                    "ilean_path": str(path.relative_to(ROOT)),
                    "ilean_sha256": content_hash,
                    "usage_count": count,
                    "attributed_usage_count": attributed,
                    "unattributed_usage_count": count - attributed,
                }
            )
    finally:
        writer.close()

    usage_path = output_dir / "usages.parquet"
    usage_sha = install_immutable(temp_path, usage_path)
    modules_frame = pl.DataFrame(module_rows).sort("module")
    modules_path = output_dir / "modules.parquet"
    with tempfile.NamedTemporaryFile(dir=output_dir, suffix=".parquet", delete=False) as handle:
        temp_modules = pathlib.Path(handle.name)
    modules_frame.write_parquet(temp_modules, compression="zstd", statistics=True)
    modules_sha = install_immutable(temp_modules, modules_path)
    manifest = {
        "schema_version": "source-graph-raw-manifest-v1",
        "graph_schema_version": SOURCE_USAGE_SCHEMA_VERSION,
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "source_format": "Lean .ilean v5 resolved references",
        "input_module_count": len(modules),
        "input_set_sha256": input_digest.hexdigest(),
        "usage_count": usage_count,
        "attributed_usage_count": attributed_count,
        "unattributed_usage_count": usage_count - attributed_count,
        "artifacts": {
            "usages": {"path": str(usage_path.relative_to(ROOT)), "sha256": usage_sha},
            "modules": {"path": str(modules_path.relative_to(ROOT)), "sha256": modules_sha},
        },
    }
    manifest_path = output_dir / "manifest.json"
    rendered = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    if manifest_path.exists() and manifest_path.read_text() != rendered:
        raise ValueError(f"immutable source-graph manifest changed: {manifest_path}")
    if not manifest_path.exists():
        manifest_path.write_text(rendered)
    return manifest


def classify_parent_usages(
    usages: pl.DataFrame, base_nodes: pl.DataFrame
) -> tuple[pl.DataFrame, pl.DataFrame, pl.DataFrame, pl.DataFrame]:
    """Partition usages by persistent parent identity and source-module agreement."""

    sort_columns = [
        column
        for column in (
            "parent_decl",
            "module",
            "target_decl",
            "start_line",
            "start_character",
        )
        if column in usages.columns
    ]
    parent_labeled = usages.filter(pl.col("parent_decl").is_not_null())
    unparented = usages.filter(pl.col("parent_decl").is_null()).sort(sort_columns)
    parent_modules = base_nodes.select(
        pl.col("name").alias("parent_decl"),
        pl.col("module").alias("parent_node_module"),
    )
    if parent_modules["parent_decl"].n_unique() != parent_modules.height:
        raise ValueError("Environment declaration names must be unique for parent attribution")
    unresolved = (
        parent_labeled.join(
            parent_modules.select("parent_decl"), on="parent_decl", how="anti"
        )
        .with_columns(pl.lit("parent_not_in_environment").alias("exclusion_reason"))
        .sort(sort_columns)
    )
    resolved = parent_labeled.join(
        parent_modules, on="parent_decl", how="inner", validate="m:1"
    )
    mismatched = (
        resolved.filter(pl.col("module") != pl.col("parent_node_module"))
        .with_columns(pl.lit("parent_module_mismatch").alias("exclusion_reason"))
        .sort(sort_columns)
    )
    attributed = (
        resolved.filter(pl.col("module") == pl.col("parent_node_module"))
        .drop("parent_node_module")
        .sort(sort_columns)
    )
    return attributed, unparented, unresolved, mismatched


def normalize_source_graph(run_kind: str) -> dict[str, Any]:
    snapshot = CONFIG["snapshot_id"]
    raw_dir = source_graph_raw_root(snapshot, run_kind)
    output_dir = source_graph_normalized_root(snapshot, run_kind)
    output_dir.mkdir(parents=True, exist_ok=True)
    deprecated_unattributed_path = output_dir / "unattributed_usages.parquet"
    if deprecated_unattributed_path.exists():
        deprecated_unattributed_path.unlink()
    usages = pl.read_parquet(raw_dir / "usages.parquet")
    unexpected_nulls = sum(
        usages[column].null_count() for column in usages.columns if column != "parent_decl"
    )
    if unexpected_nulls != 0:
        raise ValueError("source usages contain unexpected nulls")
    if usages.unique(subset=USAGE_KEY).height != usages.height:
        raise ValueError("source usages contain duplicate target ranges")

    base_dir = normalized_root(snapshot, run_kind)
    base_nodes = pl.read_parquet(base_dir / "nodes.parquet").drop("node_id")
    attributed, unparented, unresolved_parent_usages, mismatched_parent_usages = (
        classify_parent_usages(usages, base_nodes)
    )
    if usages.height != (
        attributed.height
        + unparented.height
        + unresolved_parent_usages.height
        + mismatched_parent_usages.height
    ):
        raise ValueError(
            "source usages were lost while classifying declaration-parent attribution"
        )

    all_names = (
        pl.concat(
            [
                base_nodes.select("name"),
                attributed.select(pl.col("parent_decl").alias("name")),
                usages.select(pl.col("target_decl").alias("name")),
            ]
        )
        .unique()
        .sort("name")
        .with_row_index("node_id")
        .with_columns(pl.col("node_id").cast(pl.UInt64))
    )
    nodes = (
        base_nodes.join(all_names, on="name", how="left", validate="1:1")
        .select("snapshot_id", "node_id", pl.exclude("snapshot_id", "node_id"))
        .sort("node_id")
    )
    external_nodes = (
        all_names.join(base_nodes.select("name"), on="name", how="anti")
        .join(
            usages.select(pl.col("target_decl").alias("name"), "target_module")
            .unique()
            .group_by("name")
            .agg(
                pl.col("target_module").sort().alias("target_module_hints"),
                pl.col("target_module").n_unique().alias("target_module_hint_count"),
            ),
            on="name",
            how="left",
        )
        .with_columns(
            pl.lit(snapshot).alias("snapshot_id"),
            pl.lit("not_in_extracted_corpus").alias("external_reason"),
        )
        .select(
            "snapshot_id",
            "node_id",
            "name",
            "target_module_hints",
            "target_module_hint_count",
            "external_reason",
        )
        .sort("node_id")
    )
    ids = all_names.select("node_id", "name")
    normalized_usages = (
        attributed.join(
            ids.rename({"node_id": "src_id", "name": "parent_decl"}),
            on="parent_decl",
            how="left",
            validate="m:1",
        )
        .join(
            ids.rename({"node_id": "dst_id", "name": "target_decl"}),
            on="target_decl",
            how="left",
            validate="m:1",
        )
        .select(
            "snapshot_id",
            "src_id",
            "dst_id",
            "module",
            "target_module",
            "start_line",
            "start_character",
            "end_line",
            "end_character",
        )
        .sort("src_id", "dst_id", "module", "start_line", "start_character")
    )
    edges = (
        normalized_usages.group_by("snapshot_id", "src_id", "dst_id")
        .agg(pl.len().cast(pl.UInt64).alias("multiplicity"))
        .with_columns(pl.lit("SOURCE").alias("edge_type"))
        .select("snapshot_id", "src_id", "dst_id", "edge_type", "multiplicity")
        .sort("src_id", "dst_id")
    )
    if normalized_usages.height != attributed.height:
        raise ValueError("attributed source usages were lost during ID normalization")
    if normalized_usages.select("src_id", "dst_id").null_count().sum_horizontal().item() != 0:
        raise ValueError("normalized source usages contain unresolved node IDs")
    if edges.select(pl.col("multiplicity").sum()).item() != attributed.height:
        raise ValueError("edge multiplicities do not preserve attributed source usages")
    if edges.unique(subset=["snapshot_id", "src_id", "dst_id"]).height != edges.height:
        raise ValueError("normalized source graph contains duplicate edge rows")
    if edges.filter(pl.col("multiplicity") == 0).height:
        raise ValueError("normalized source graph contains zero-multiplicity edges")
    modules = pl.read_parquet(raw_dir / "modules.parquet").sort("module")
    target_module_ambiguity_count = (
        usages.select("target_decl", "target_module")
        .unique()
        .group_by("target_decl")
        .agg(pl.col("target_module").n_unique().alias("module_hint_count"))
        .filter(pl.col("module_hint_count") > 1)
        .height
    )

    frames = {
        "nodes": nodes,
        "edges": edges,
        "usages": normalized_usages,
        "unparented_usages": unparented,
        "unresolved_parent_usages": unresolved_parent_usages,
        "mismatched_parent_usages": mismatched_parent_usages,
        "external_nodes": external_nodes,
        "modules": modules,
    }
    artifacts: dict[str, Any] = {}
    for name, frame in frames.items():
        path = output_dir / f"{name}.parquet"
        frame.write_parquet(path, compression="zstd", statistics=True)
        artifacts[name] = {
            "path": str(path.relative_to(ROOT)),
            "rows": frame.height,
            "sha256": sha256(path),
            "null_counts": {column: frame[column].null_count() for column in frame.columns},
        }
    manifest = {
        "schema_version": "source-graph-normalized-manifest-v2",
        "graph_schema_version": SOURCE_GRAPH_SCHEMA_VERSION,
        "node_source_graph_schema_version": GRAPH_SCHEMA_VERSION,
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "edge_direction": "consumer_declaration_to_resolved_target_declaration",
        "edge_type": "SOURCE",
        "multiplicity": "distinct_resolved_source_ranges",
        "parent_labeled_usage_count": int(usages["parent_decl"].is_not_null().sum()),
        "attributed_usage_count": attributed.height,
        "unparented_usage_count": unparented.height,
        "unresolved_parent_usage_count": unresolved_parent_usages.height,
        "parent_module_mismatch_usage_count": mismatched_parent_usages.height,
        "target_names_with_multiple_module_hints": target_module_ambiguity_count,
        "edge_multiplicity_sum": edges.select(pl.col("multiplicity").sum()).item(),
        "self_loop_edge_count": edges.filter(pl.col("src_id") == pl.col("dst_id")).height,
        "self_loop_multiplicity": edges.filter(pl.col("src_id") == pl.col("dst_id")).select(
            pl.col("multiplicity").sum()
        ).item()
        or 0,
        "artifacts": artifacts,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    run_dir = run_results_root(run_kind)
    run_dir.mkdir(parents=True, exist_ok=True)
    summary_path = run_dir / "source-graph-summary.json"
    summary_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def build_source_graph(run_kind: str) -> dict[str, Any]:
    raw = extract_usages(run_kind)
    normalized = normalize_source_graph(run_kind)
    return {"raw": raw, "normalized": normalized}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    result = build_source_graph("smoke" if args.smoke else "full")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
