from __future__ import annotations

import argparse
import json
import math
import tomllib
import warnings
from typing import Any

import numpy as np
import polars as pl
import scipy.stats
import statsmodels.api as sm

from knowledge_reuse.analysis.concentration import gini, hhi, top_share
from knowledge_reuse.analysis.powerlaw import fit_tail
from knowledge_reuse.sources.lean_mathlib.layout import (
    CONFIG_PATH,
    normalized_root,
    run_results_root,
)


CONFIG = tomllib.loads(CONFIG_PATH.read_text())

EXAMPLE_COLUMNS = (
    "example_id",
    "concept",
    "role",
    "selection_rule",
    "snapshot_id",
    "src_id",
    "src_name",
    "src_module",
    "src_domain",
    "src_kind",
    "dst_id",
    "dst_name",
    "dst_module",
    "dst_domain",
    "dst_kind",
    "edge_type",
    "node_id",
    "node_name",
    "node_module",
    "node_domain",
    "node_kind",
    "has_value",
    "source_bytes",
    "type_expr_nodes",
    "value_expr_nodes",
    "in_degree_all",
    "evidence",
    "source_locator",
    "explanation",
    "caveat",
)


def _node_record(frame: pl.DataFrame, name: str) -> dict[str, Any] | None:
    selected = frame.filter(pl.col("name") == name)
    return selected.row(0, named=True) if selected.height else None


def _example_row(**values: Any) -> dict[str, Any]:
    return {column: values.get(column) for column in EXAMPLE_COLUMNS}


def build_report_examples(
    nodes: pl.DataFrame, edges: pl.DataFrame, node_metrics: pl.DataFrame, snapshot: str
) -> list[dict[str, Any]]:
    """Build deterministic, evidence-addressable examples for the research report."""
    examples: list[dict[str, Any]] = []
    candidates = [
        (
            "node.definition.small",
            "declaration node",
            "small",
            "Set",
            "固定 snapshot 候选；缺失时选择最小的有 value definition",
            "一个结构较小但高复用的 definition 节点。",
        ),
        (
            "node.no_value",
            "value null semantics",
            "null",
            "CategoryTheory.Category",
            "固定 snapshot 候选；缺失时选择首个无 value 的 declaration",
            "没有 value 的 inductive，其 value complexity 是 null 而不是 0。",
        ),
        (
            "node.definition.value",
            "definition value",
            "medium",
            "Semiring.toNonAssocSemiring",
            "固定 snapshot 候选；缺失时选择接近 value complexity 中位数的 definition",
            "同时具有 type 与 definition body 的真实节点。",
        ),
        (
            "node.complexity.high",
            "Expr workload",
            "high",
            "CategoryTheory.Limits.colimitLimitToLimitColimit_surjective",
            "固定 snapshot 候选；缺失时选择非生成节点中 value complexity 最大者",
            "真实高工作量 theorem，展示 tree-occurrence 计数为何需要缓存。",
        ),
    ]
    for example_id, concept, role, preferred, rule, explanation in candidates:
        record = _node_record(node_metrics, preferred)
        if record is None:
            if role == "null":
                fallback = node_metrics.filter(~pl.col("has_value")).sort("name")
            elif role == "high":
                fallback = node_metrics.filter(
                    ~pl.col("is_generated") & pl.col("value_expr_nodes").is_not_null()
                ).sort("value_expr_nodes", "name", descending=[True, False])
            elif role == "medium":
                median = node_metrics["value_expr_nodes"].drop_nulls().median() or 0
                fallback = (
                    node_metrics.filter(
                        pl.col("is_definition") & pl.col("value_expr_nodes").is_not_null()
                    )
                    .with_columns(
                        (pl.col("value_expr_nodes").cast(pl.Int128) - int(median))
                        .abs()
                        .alias("distance")
                    )
                    .sort("distance", "name")
                )
            else:
                fallback = node_metrics.filter(
                    pl.col("is_definition") & pl.col("has_value")
                ).sort("type_expr_nodes", "name")
            if fallback.is_empty():
                continue
            record = fallback.row(0, named=True)
        examples.append(
            _example_row(
                example_id=example_id,
                concept=concept,
                role=role,
                selection_rule=rule,
                snapshot_id=snapshot,
                node_id=record["node_id"],
                node_name=record["name"],
                node_module=record["module"],
                node_domain=record["domain"],
                node_kind=record["kind"],
                has_value=record["has_value"],
                source_bytes=record["source_bytes"],
                type_expr_nodes=record["type_expr_nodes"],
                value_expr_nodes=record["value_expr_nodes"],
                in_degree_all=record["in_degree_all"],
                evidence=f"metrics/node_metrics.parquet#node_id={record['node_id']}",
                source_locator=f"{record['source_file']}::{record['name']}",
                explanation=explanation,
                caveat="该单例用于解释概念，不能替代总体统计。",
            )
        )

    edge_candidates = [
        (
            "edge.value.theorem_to_theorem",
            "VALUE edge",
            "constantCoeff_xInTermsOfW",
            "map_pow",
            "VALUE",
            "theorem proof/value 对 theorem 的真实复用。",
        ),
        (
            "edge.type.theorem_to_definition",
            "TYPE edge",
            "padicValRat.of_nat",
            "padicValNat",
            "TYPE",
            "theorem statement/type 对 definition 的真实依赖。",
        ),
    ]
    needed_names = {
        name
        for _, _, src_name, dst_name, _, _ in edge_candidates
        for name in (src_name, dst_name)
    } | {"DFunLike.coe"}
    node_by_name = {
        row["name"]: row
        for row in nodes.filter(pl.col("name").is_in(sorted(needed_names))).iter_rows(
            named=True
        )
    }
    for example_id, concept, src_name, dst_name, edge_type, explanation in edge_candidates:
        src, dst = node_by_name.get(src_name), node_by_name.get(dst_name)
        if src is None or dst is None:
            continue
        found = edges.filter(
            (pl.col("src_id") == src["node_id"])
            & (pl.col("dst_id") == dst["node_id"])
            & (pl.col("edge_type") == edge_type)
        )
        if found.is_empty():
            continue
        examples.append(
            _example_row(
                example_id=example_id,
                concept=concept,
                role="real_edge",
                selection_rule="固定 v4.32.1 候选，并在当前 normalized edge table 中精确验证",
                snapshot_id=snapshot,
                src_id=src["node_id"],
                src_name=src_name,
                src_module=src["module"],
                src_domain=src["domain"],
                src_kind=src["kind"],
                dst_id=dst["node_id"],
                dst_name=dst_name,
                dst_module=dst["module"],
                dst_domain=dst["domain"],
                dst_kind=dst["kind"],
                edge_type=edge_type,
                evidence=(
                    "normalized/edges.parquet#"
                    f"src_id={src['node_id']},dst_id={dst['node_id']},edge_type={edge_type}"
                ),
                source_locator=f"{src['source_file']}::{src_name}",
                explanation=explanation,
                caveat="一条边证明该依赖实例存在，不证明总体分布。",
            )
        )

    reuse_target = node_by_name.get("DFunLike.coe")
    if reuse_target is None:
        top = node_metrics.sort("in_degree_all", "name", descending=[True, False]).row(
            0, named=True
        )
        reuse_target = _node_record(nodes, top["name"])
        assert reuse_target is not None
    incoming = edges.filter(pl.col("dst_id") == reuse_target["node_id"]).sort(
        "src_id", "edge_type"
    ).head(5)
    incoming_ids = incoming["src_id"].to_list() + [reuse_target["node_id"]]
    node_by_id = {
        row["node_id"]: row
        for row in nodes.filter(pl.col("node_id").is_in(incoming_ids)).iter_rows(named=True)
    }
    for index, edge in enumerate(incoming.iter_rows(named=True), 1):
        src = node_by_id[edge["src_id"]]
        examples.append(
            _example_row(
                example_id=f"reuse.incoming.{index:02d}",
                concept="reuse indegree",
                role="incoming_edge",
                selection_rule="目标 DFunLike.coe；incoming typed edges 按 src_id、edge_type 排序取前 5",
                snapshot_id=snapshot,
                src_id=src["node_id"],
                src_name=src["name"],
                src_module=src["module"],
                src_domain=src["domain"],
                src_kind=src["kind"],
                dst_id=reuse_target["node_id"],
                dst_name=reuse_target["name"],
                dst_module=reuse_target["module"],
                dst_domain=reuse_target["domain"],
                dst_kind=reuse_target["kind"],
                edge_type=edge["edge_type"],
                in_degree_all=_node_record(node_metrics, reuse_target["name"])["in_degree_all"],
                evidence=(
                    "normalized/edges.parquet#"
                    f"src_id={src['node_id']},dst_id={reuse_target['node_id']},"
                    f"edge_type={edge['edge_type']}"
                ),
                source_locator=f"{src['source_file']}::{src['name']}",
                explanation="每个不同 source declaration 为 target 的 unique reuse 增加一次。",
                caveat="这里只展示 5 条确定性样例，不是完整 incoming edge list。",
            )
        )
    return examples


def append_domain_examples(
    examples: list[dict[str, Any]],
    internal_edges: pl.DataFrame,
    nodes: pl.DataFrame,
    snapshot: str,
) -> None:
    selected = pl.concat(
        [
            internal_edges.filter(pl.col("src_domain") != pl.col("dst_domain")).head(2),
            internal_edges.filter(pl.col("src_domain") == pl.col("dst_domain")).head(1),
        ]
    )
    selected_ids = selected["src_id"].to_list() + selected["dst_id"].to_list()
    node_by_id = {
        row["node_id"]: row
        for row in nodes.filter(pl.col("node_id").is_in(selected_ids)).iter_rows(named=True)
    }
    for index, edge in enumerate(selected.iter_rows(named=True), 1):
        src, dst = node_by_id[edge["src_id"]], node_by_id[edge["dst_id"]]
        examples.append(
            _example_row(
                example_id=f"domain.edge.{index:02d}",
                concept="domain dependency matrix",
                role="cross_domain" if src["domain"] != dst["domain"] else "within_domain",
                selection_rule="normalized internal edges 的稳定顺序：前两条跨领域边与第一条领域内边",
                snapshot_id=snapshot,
                src_id=src["node_id"],
                src_name=src["name"],
                src_module=src["module"],
                src_domain=src["domain"],
                src_kind=src["kind"],
                dst_id=dst["node_id"],
                dst_name=dst["name"],
                dst_module=dst["module"],
                dst_domain=dst["domain"],
                dst_kind=dst["kind"],
                edge_type=edge["edge_type"],
                evidence=(
                    "normalized/edges.parquet#"
                    f"src_id={src['node_id']},dst_id={dst['node_id']},"
                    f"edge_type={edge['edge_type']}"
                ),
                source_locator=f"{src['source_file']}::{src['name']}",
                explanation="该边使对应 src_domain→dst_domain matrix cell 增加 1。",
                caveat="单条边只解释矩阵累加规则，不代表领域间总体强度。",
            )
        )


def with_node_metrics(nodes: pl.DataFrame, edges: pl.DataFrame) -> pl.DataFrame:
    internal_ids = nodes.select("node_id")
    internal_edges = edges.join(
        internal_ids.rename({"node_id": "dst_id"}), on="dst_id", how="inner"
    )
    indegree = internal_edges.group_by("dst_id").agg(
        pl.col("src_id").n_unique().alias("in_degree_all"),
        pl.col("src_id").filter(pl.col("edge_type") == "TYPE").n_unique().alias("in_degree_type"),
        pl.col("src_id").filter(pl.col("edge_type") == "VALUE").n_unique().alias("in_degree_value"),
    )
    outdegree = edges.group_by("src_id").agg(
        pl.col("dst_id").n_unique().alias("out_degree_all")
    )
    return (
        nodes.join(indegree, left_on="node_id", right_on="dst_id", how="left")
        .join(outdegree, left_on="node_id", right_on="src_id", how="left")
        .with_columns(
            pl.col(column).fill_null(0).cast(pl.UInt64)
            for column in ("in_degree_all", "in_degree_type", "in_degree_value", "out_degree_all")
        )
    )


def population_degrees(
    nodes: pl.DataFrame, edges: pl.DataFrame, node_metrics: pl.DataFrame
) -> dict[str, np.ndarray]:
    node_kind = nodes.select("node_id", "kind")
    typed = edges.join(
        node_kind.rename({"node_id": "src_id", "kind": "src_kind"}), on="src_id", how="inner"
    ).join(node_kind.rename({"node_id": "dst_id", "kind": "dst_kind"}), on="dst_id", how="inner")

    def dst_degrees(frame: pl.DataFrame) -> np.ndarray:
        counts = frame.group_by("dst_id").agg(pl.col("src_id").n_unique().alias("degree"))
        return counts["degree"].to_numpy()

    populations = {
        "all_declarations": node_metrics["in_degree_all"].to_numpy(),
        "theorem_only": node_metrics.filter(pl.col("is_theorem"))["in_degree_all"].to_numpy(),
        "definition_only": node_metrics.filter(pl.col("is_definition"))["in_degree_all"].to_numpy(),
        "type_graph": dst_degrees(typed.filter(pl.col("edge_type") == "TYPE")),
        "value_graph": dst_degrees(typed.filter(pl.col("edge_type") == "VALUE")),
        "theorem_to_theorem": dst_degrees(
            typed.filter((pl.col("src_kind") == "theorem") & (pl.col("dst_kind") == "theorem"))
        ),
        "theorem_to_definition": dst_degrees(
            typed.filter(
                (pl.col("src_kind") == "theorem")
                & pl.col("dst_kind").is_in(["definition", "opaque"])
            )
        ),
    }
    for domain in sorted(nodes["domain"].unique().drop_nulls().to_list()):
        populations[f"domain:{domain}"] = node_metrics.filter(pl.col("domain") == domain)[
            "in_degree_all"
        ].to_numpy()
    return populations


def fit_regression(node_metrics: pl.DataFrame, length_column: str) -> dict[str, Any]:
    frame = node_metrics.drop_nulls([length_column, "domain", "kind"])
    result: dict[str, Any] = {
        "length_metric": length_column,
        "n": frame.height,
        "status": "insufficient_observations",
    }
    if frame.height < 30:
        return result
    kind = frame.select(pl.col("kind").cast(pl.Categorical).to_physical()).to_numpy().ravel()
    domain = frame.select(pl.col("domain").cast(pl.Categorical).to_physical()).to_numpy().ravel()
    kind_dummies = np.eye(int(kind.max()) + 1)[kind.astype(int)][:, 1:]
    domain_dummies = np.eye(int(domain.max()) + 1)[domain.astype(int)][:, 1:]
    length = np.log1p(frame[length_column].to_numpy().astype(float))
    design = np.column_stack((np.ones(frame.height), length, kind_dummies, domain_dummies))
    response = frame["in_degree_all"].to_numpy().astype(float)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            model = sm.NegativeBinomial(response, design).fit(disp=False, maxiter=200)
        low, high = model.conf_int()[1]
        result.update(
            {
                "status": "ok" if model.mle_retvals.get("converged") else "not_converged",
                "coefficient": float(model.params[1]),
                "std_error": float(model.bse[1]),
                "ci_low": float(low),
                "ci_high": float(high),
                "p_value": float(model.pvalues[1]),
                "alpha_dispersion": float(model.params[-1]),
                "controls": "kind+domain",
            }
        )
    except (ValueError, np.linalg.LinAlgError) as error:
        result.update({"status": "failed", "error": str(error)})
    finite = all(
        math.isfinite(float(result.get(key, math.nan)))
        for key in ("coefficient", "std_error", "ci_low", "ci_high", "p_value")
    )
    if result["status"] != "ok" or not finite:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                fallback = sm.GLM(
                    response,
                    design,
                    family=sm.families.NegativeBinomial(alpha=1.0),
                ).fit(maxiter=200)
            low, high = fallback.conf_int()[1]
            result.update(
                {
                    "status": "ok_glm_fixed_dispersion",
                    "coefficient": float(fallback.params[1]),
                    "std_error": float(fallback.bse[1]),
                    "ci_low": float(low),
                    "ci_high": float(high),
                    "p_value": float(fallback.pvalues[1]),
                    "alpha_dispersion": 1.0,
                    "controls": "kind+domain",
                    "error": None,
                }
            )
        except (ValueError, np.linalg.LinAlgError) as error:
            result.update({"status": "failed", "error": str(error)})
    return result


def correlations(node_metrics: pl.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for length in ("source_bytes", "source_tokens", "type_expr_nodes", "value_expr_nodes"):
        frame = node_metrics.drop_nulls([length])
        coefficient, p_value = scipy.stats.spearmanr(
            frame[length].to_numpy(), frame["in_degree_all"].to_numpy()
        )
        rows.append(
            {
                "length_metric": length,
                "n": frame.height,
                "spearman_rho": float(coefficient),
                "p_value": float(p_value),
            }
        )
    return rows


def length_bins(node_metrics: pl.DataFrame) -> pl.DataFrame:
    frames = []
    for length in ("source_bytes", "source_tokens", "type_expr_nodes", "value_expr_nodes"):
        frame = node_metrics.drop_nulls([length]).filter(pl.col(length) > 0)
        if frame.is_empty():
            continue
        frame = frame.with_columns(
            pl.col(length).log(base=2).floor().cast(pl.Int32).alias("log2_bin")
        )
        frames.append(
            frame.group_by("log2_bin")
            .agg(
                pl.len().alias("n"),
                pl.col(length).median().alias("length_median"),
                pl.col("in_degree_all").median().alias("reuse_median"),
                pl.col("in_degree_all").quantile(0.25).alias("reuse_q25"),
                pl.col("in_degree_all").quantile(0.75).alias("reuse_q75"),
            )
            .with_columns(pl.lit(length).alias("length_metric"))
        )
    return pl.concat(frames).select(
        "length_metric", "log2_bin", "n", "length_median", "reuse_median", "reuse_q25", "reuse_q75"
    )


def analyze(run_kind: str) -> dict[str, Any]:
    snapshot = CONFIG["snapshot_id"]
    parquet_dir = normalized_root(snapshot, run_kind)
    run_dir = run_results_root(run_kind)
    metrics_dir = run_dir / "metrics"
    tables_dir = run_dir / "tables"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    nodes = pl.read_parquet(parquet_dir / "nodes.parquet")
    edges = pl.read_parquet(parquet_dir / "edges.parquet")
    modules = pl.read_parquet(parquet_dir / "modules.parquet")
    node_metrics = with_node_metrics(nodes, edges)
    node_metrics.write_parquet(metrics_dir / "node_metrics.parquet", compression="zstd")
    report_examples = build_report_examples(nodes, edges, node_metrics, snapshot)

    degree = node_metrics["in_degree_all"].to_numpy()
    view_metrics = []
    for view, frame in (
        ("ALL", node_metrics),
        ("NO_GENERATED", node_metrics.filter(~pl.col("is_generated"))),
        ("THEOREM_ONLY", node_metrics.filter(pl.col("is_theorem"))),
        ("DEF_ONLY", node_metrics.filter(pl.col("is_definition"))),
        (
            "THEOREM_AND_DEF",
            node_metrics.filter(pl.col("is_theorem") | pl.col("is_definition")),
        ),
        (
            "USER_FACING_APPROX",
            node_metrics.filter(~pl.col("is_generated") & ~pl.col("is_internal")),
        ),
    ):
        values = frame["in_degree_all"].to_numpy()
        view_metrics.append(
            {
                "view": view,
                "nodes": frame.height,
                "gini": gini(values),
                "hhi": hhi(values),
                "top_1pct_share": top_share(values, 0.01),
                "top_5pct_share": top_share(values, 0.05),
                "top_10pct_share": top_share(values, 0.10),
            }
        )
    pl.DataFrame(view_metrics).write_parquet(metrics_dir / "view_metrics.parquet", compression="zstd")

    populations = population_degrees(nodes, edges, node_metrics)
    fits = pl.DataFrame([fit_tail(values, name) for name, values in populations.items()])
    fits.write_parquet(metrics_dir / "powerlaw_fits.parquet", compression="zstd")
    regressions = pl.DataFrame(
        [fit_regression(node_metrics, length) for length in ("source_bytes", "type_expr_nodes", "value_expr_nodes")]
    )
    regressions.write_parquet(metrics_dir / "regressions.parquet", compression="zstd")
    correlation_rows = correlations(node_metrics)
    pl.DataFrame(correlation_rows).write_parquet(
        metrics_dir / "length_correlations.parquet", compression="zstd"
    )
    length_bins(node_metrics).write_parquet(metrics_dir / "length_binned.parquet", compression="zstd")

    node_domain = nodes.select("node_id", "domain")
    internal_edges = edges.join(
        node_domain.rename({"node_id": "src_id", "domain": "src_domain"}),
        on="src_id",
        how="inner",
    ).join(
        node_domain.rename({"node_id": "dst_id", "domain": "dst_domain"}),
        on="dst_id",
        how="inner",
    )
    domain_matrix = (
        internal_edges.group_by("src_domain", "dst_domain", "edge_type")
        .agg(pl.len().alias("edge_count"))
        .with_columns(
            (pl.col("edge_count") / pl.col("edge_count").sum().over("src_domain")).alias(
                "row_share"
            )
        )
        .sort("src_domain", "dst_domain", "edge_type")
    )
    domain_matrix.write_parquet(tables_dir / "domain_matrix.parquet", compression="zstd")
    append_domain_examples(report_examples, internal_edges, nodes, snapshot)
    pl.DataFrame(report_examples).select(EXAMPLE_COLUMNS).write_parquet(
        tables_dir / "report_examples.parquet", compression="zstd"
    )
    domain_rows = []
    for domain in sorted(nodes["domain"].unique().drop_nulls().to_list()):
        domain_nodes = node_metrics.filter(pl.col("domain") == domain)
        outbound = domain_matrix.filter(pl.col("src_domain") == domain)
        probabilities = (
            outbound.group_by("dst_domain")
            .agg(pl.col("edge_count").sum())
            .with_columns(pl.col("edge_count") / pl.col("edge_count").sum())
        )["edge_count"].to_numpy()
        entropy = float(-(probabilities * np.log(probabilities)).sum()) if probabilities.size else 0.0
        normalized_entropy = entropy / math.log(domain_nodes.height) if domain_nodes.height > 1 else 0.0
        values = domain_nodes["in_degree_all"].to_numpy()
        fit_row = fits.filter(pl.col("population") == f"domain:{domain}")
        internal_count = outbound.filter(pl.col("src_domain") == pl.col("dst_domain"))[
            "edge_count"
        ].sum()
        total_outbound = outbound["edge_count"].sum()
        domain_rows.append(
            {
                "domain": domain,
                "node_count": domain_nodes.height,
                "edge_count": int(total_outbound or 0),
                "gini": gini(values),
                "top_1pct_share": top_share(values, 0.01),
                "internal_dependency_share": (
                    float(internal_count / total_outbound) if total_outbound else 0.0
                ),
                "outbound_domain_diversity": outbound["dst_domain"].n_unique(),
                "reference_entropy_proxy": normalized_entropy,
                "alpha": fit_row["alpha"][0] if fit_row.height else None,
                "xmin": fit_row["xmin"][0] if fit_row.height else None,
            }
        )
    pl.DataFrame(domain_rows).write_parquet(metrics_dir / "domain_metrics.parquet", compression="zstd")

    top_reuse = node_metrics.sort("in_degree_all", "name", descending=[True, False]).head(100)
    top_reuse.write_csv(tables_dir / "top_reuse.csv")
    summary = {
        "schema_version": "analysis-summary-v1",
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "module_count": modules.height,
        "declaration_count": nodes.height,
        "declaration_counts_by_kind": dict(
            nodes.group_by("kind").len().sort("kind").iter_rows()
        ),
        "edge_count": edges.height,
        "type_edge_count": edges.filter(pl.col("edge_type") == "TYPE").height,
        "value_edge_count": edges.filter(pl.col("edge_type") == "VALUE").height,
        "self_loop_count": edges.filter(pl.col("src_id") == pl.col("dst_id")).height,
        "zero_indegree_fraction": float(np.count_nonzero(degree == 0) / degree.size),
        "zero_outdegree_fraction": float(
            np.count_nonzero(node_metrics["out_degree_all"].to_numpy() == 0) / nodes.height
        ),
        "isolated_fraction": float(
            np.count_nonzero(
                (degree == 0) & (node_metrics["out_degree_all"].to_numpy() == 0)
            )
            / nodes.height
        ),
        "reuse_concentration": view_metrics[0],
        "length_correlations": correlation_rows,
        "reference_entropy_label": "H*ref empirical operational proxy; not theoretical H",
    }
    (metrics_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    (run_dir / "analysis-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    summary = analyze("smoke" if args.smoke else "full")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
