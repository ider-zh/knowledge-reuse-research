"""Export a compact, explainable public dataset for the research site."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
from typing import Any

import polars as pl

from knowledge_reuse.sources.lean_mathlib.layout import (
    CONFIG_PATH,
    normalized_root,
    run_results_root,
)


NODE_COLUMNS = [
    "name",
    "module",
    "domain",
    "kind",
    "has_value",
    "source_tokens",
    "type_expr_unique_ptr_nodes",
    "value_expr_unique_ptr_nodes",
    "value_expr_tree_occurrences",
    "in_degree_all",
    "in_degree_type",
    "in_degree_value",
    "out_degree_all",
]


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: pathlib.Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def public_node_sample(nodes: pl.DataFrame) -> pl.DataFrame:
    """Purposefully sample interpretable nodes; this is not a random sample."""

    selected = []
    for reason, frame in (
        (
            "全库复用入度前 120",
            nodes.sort("in_degree_all", "name", descending=[True, False]).head(120),
        ),
        (
            "每个路径领域复用入度前 5",
            nodes.sort("domain", "in_degree_all", "name", descending=[False, True, False])
            .group_by("domain", maintain_order=True)
            .head(5),
        ),
        (
            "Value 展开树规模前 60",
            nodes.drop_nulls("value_expr_tree_occurrences")
            .sort("value_expr_tree_occurrences", "name", descending=[True, False])
            .head(60),
        ),
    ):
        selected.append(
            frame.select("node_id", *NODE_COLUMNS).with_columns(
                pl.lit(reason).alias("sample_reason")
            )
        )

    combined = pl.concat(selected)
    return (
        combined.group_by("node_id")
        .agg(
            *[pl.col(column).first() for column in NODE_COLUMNS],
            pl.col("sample_reason").unique().sort().str.join("；"),
        )
        .sort("in_degree_all", "name", descending=[True, False])
    )


def external_target_sample(
    edges: pl.DataFrame, external_nodes: pl.DataFrame, limit: int = 200
) -> pl.DataFrame:
    """Return the most frequently referenced explicit external targets."""

    return (
        edges.join(
            external_nodes.select("node_id", "name"),
            left_on="dst_id",
            right_on="node_id",
            how="inner",
        )
        .group_by("dst_id", "name")
        .agg(
            pl.col("src_id").n_unique().alias("unique_consumer_count"),
            pl.len().alias("typed_edge_count"),
            (pl.col("edge_type") == "TYPE").sum().alias("type_edge_count"),
            (pl.col("edge_type") == "VALUE").sum().alias("value_edge_count"),
        )
        .sort("unique_consumer_count", "name", descending=[True, False])
        .head(limit)
        .with_columns(pl.lit(f"外部目标按 unique consumers 排名前 {limit}").alias("sample_reason"))
    )


def domain_edge_sample(edges: pl.DataFrame, nodes: pl.DataFrame, per_cell: int = 3) -> pl.DataFrame:
    """Keep deterministic examples for every observed internal domain cell."""

    identities = nodes.select("node_id", "name", "module", "domain", "kind")
    pairs = edges.group_by("src_id", "dst_id").agg(
        pl.col("edge_type").unique().sort().str.join("+").alias("edge_types")
    )
    enriched = (
        pairs.join(
            identities.rename(
                {
                    "node_id": "src_id",
                    "name": "src_name",
                    "module": "src_module",
                    "domain": "src_domain",
                    "kind": "src_kind",
                }
            ),
            on="src_id",
            how="inner",
        )
        .join(
            identities.rename(
                {
                    "node_id": "dst_id",
                    "name": "dst_name",
                    "module": "dst_module",
                    "domain": "dst_domain",
                    "kind": "dst_kind",
                }
            ),
            on="dst_id",
            how="inner",
        )
        .sort("src_domain", "dst_domain", "src_name", "dst_name")
        .with_columns(pl.int_range(pl.len()).over("src_domain", "dst_domain").alias("cell_rank"))
        .filter(pl.col("cell_rank") < per_cell)
        .with_columns(
            (pl.col("src_domain") != pl.col("dst_domain")).alias("is_cross_domain"),
            pl.lit(
                f"每个非空 source-domain → target-domain cell 按完整名称排序取前 {per_cell} 个唯一 pair"
            ).alias("sample_reason"),
        )
    )
    return enriched


def typed_edge_sample(
    edges: pl.DataFrame,
    nodes: pl.DataFrame,
    external_nodes: pl.DataFrame,
    per_group: int = 2,
) -> pl.DataFrame:
    """Keep typed-edge examples for internal and external target groups."""

    identities = nodes.select("node_id", "name", "module", "domain", "kind")
    targets = pl.concat(
        [
            identities,
            external_nodes.select("node_id", "name").with_columns(
                pl.lit(None, dtype=pl.String).alias("module"),
                pl.lit("EXTERNAL").alias("domain"),
                pl.lit("external").alias("kind"),
            ),
        ]
    )
    return (
        edges.join(
            identities.rename(
                {
                    "node_id": "src_id",
                    "name": "src_name",
                    "module": "src_module",
                    "domain": "src_domain",
                    "kind": "src_kind",
                }
            ),
            on="src_id",
            how="inner",
        )
        .join(
            targets.rename(
                {
                    "node_id": "dst_id",
                    "name": "dst_name",
                    "module": "dst_module",
                    "domain": "dst_domain",
                    "kind": "dst_kind",
                }
            ),
            on="dst_id",
            how="inner",
        )
        .sort("edge_type", "src_domain", "dst_domain", "src_name", "dst_name")
        .with_columns(
            pl.int_range(pl.len()).over("edge_type", "src_domain", "dst_domain").alias("group_rank")
        )
        .filter(pl.col("group_rank") < per_group)
        .with_columns(
            (pl.col("dst_domain") == "EXTERNAL").alias("is_external_target"),
            pl.lit(
                f"每个 edge_type × source domain × target domain 分组按完整名称排序取前 {per_group} 条"
            ).alias("sample_reason"),
        )
    )


def export_site(output: pathlib.Path, run_kind: str = "full") -> dict[str, Any]:
    import tomllib

    config = tomllib.loads(CONFIG_PATH.read_text())
    snapshot = config["snapshot_id"]
    run_dir = run_results_root(run_kind)
    metrics_dir = run_dir / "metrics"
    tables_dir = run_dir / "tables"
    normalized_dir = normalized_root(snapshot, run_kind)
    output.mkdir(parents=True, exist_ok=True)

    summary = json.loads((metrics_dir / "summary.json").read_text())
    quality = json.loads((metrics_dir / "data_quality.json").read_text())
    report_summary = json.loads((run_dir / "report-summary.json").read_text())
    claims = json.loads((run_dir / "report" / "claims.json").read_text())
    nodes = pl.read_parquet(metrics_dir / "node_metrics.parquet")
    normalized_nodes = pl.read_parquet(normalized_dir / "nodes.parquet")
    edges = pl.read_parquet(normalized_dir / "edges.parquet")
    external_nodes = pl.read_parquet(normalized_dir / "external_nodes.parquet")
    domains = pl.read_parquet(metrics_dir / "domain_metrics.parquet").sort(
        "node_count", descending=True
    )
    domain_matrix = pl.read_parquet(tables_dir / "domain_reuse_matrix.parquet").sort(
        "src_domain", "dependency_pair_count", "dst_domain", descending=[False, True, False]
    )
    kind_metrics = pl.read_parquet(metrics_dir / "kind_reuse_metrics.parquet").sort(
        "node_count", descending=True
    )

    node_sample = public_node_sample(nodes)
    external_sample = external_target_sample(edges, external_nodes)
    edge_sample = domain_edge_sample(edges, normalized_nodes)
    typed_sample = typed_edge_sample(edges, normalized_nodes, external_nodes)

    files = {
        "overview.json": {
            "schema_version": "research-site-overview-v1",
            "snapshot_id": snapshot,
            "run_kind": run_kind,
            "headline_metrics": {
                "internal_declarations": summary["declaration_count"],
                "external_targets": quality["external_node_count"],
                "typed_edges": summary["edge_count"],
                "unique_dependency_pairs": summary["all_unique_pair_count"],
                "modules": summary["module_count"],
            },
            "audit": {
                "graph_complete": report_summary["graph_complete"],
                "provenance_complete": report_summary["provenance_complete"],
                "status": report_summary["audit_status"],
            },
            "domain_algorithm": {
                "classification": "Mathlib.X... → X；非 Mathlib module → 第一段",
                "edge_direction": "consumer/source domain → dependency/target domain",
                "population": "两端均为 configured corpus 内部 declaration 的 edges",
                "pair_unit": "同一 (src_id,dst_id) 的 TYPE/VALUE 先折叠为一个 dependency pair",
                "cell_count": "按 (src_domain,dst_domain) 分组计算唯一 pair 数",
                "row_share": "cell_count / 同一 src_domain 发出的全部内部唯一 pair",
                "external_policy": "external target 没有可靠 module/domain，不进入领域矩阵，也不被分配 Other",
            },
            "sampling_policy": {
                "nodes": "目的性样本：复用头部、各领域头部、Value 展开极值；不是随机代表性样本",
                "external_targets": "按 unique consumer count 取前 200",
                "domain_edges": "每个非空领域 cell 按完整 source/target 名排序取前 3 个唯一 pair",
                "typed_edges": "每个 TYPE/VALUE × 来源领域 × 目标领域分组按完整名称取前 2 条；保留 EXTERNAL 组",
                "warning": "站点样本用于解释和局部核查；总体结论只读取完整 derived metrics",
            },
            "claims": claims["claims"],
            "domains": domains.to_dicts(),
            "domain_matrix": domain_matrix.to_dicts(),
            "kind_metrics": kind_metrics.to_dicts(),
        },
        "nodes.json": {
            "schema_version": "research-site-node-sample-v1",
            "population_count": summary["declaration_count"],
            "published_count": node_sample.height,
            "rows": node_sample.to_dicts(),
        },
        "external-targets.json": {
            "schema_version": "research-site-external-sample-v1",
            "population_count": quality["external_node_count"],
            "published_count": external_sample.height,
            "rows": external_sample.to_dicts(),
        },
        "domain-edge-samples.json": {
            "schema_version": "research-site-domain-edge-sample-v1",
            "population_count": summary["all_unique_pair_count"],
            "internal_population_count": int(domain_matrix["dependency_pair_count"].sum()),
            "published_count": edge_sample.height,
            "rows": edge_sample.to_dicts(),
        },
        "typed-edge-samples.json": {
            "schema_version": "research-site-typed-edge-sample-v1",
            "population_count": summary["edge_count"],
            "published_count": typed_sample.height,
            "rows": typed_sample.to_dicts(),
        },
    }
    for name, payload in files.items():
        write_json(output / name, payload)

    manifest = {
        "schema_version": "research-site-data-manifest-v1",
        "source_id": "lean_mathlib",
        "experiment_id": "lean_mathlib_v1",
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "files": {
            name: {
                "bytes": (output / name).stat().st_size,
                "sha256": sha256(output / name),
            }
            for name in files
        },
    }
    write_json(output / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=pathlib.Path,
        default=pathlib.Path("apps/research-site/public/datasets/lean_mathlib_v1/mathlib-v4.32.1"),
    )
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    manifest = export_site(args.output, "smoke" if args.smoke else "full")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
