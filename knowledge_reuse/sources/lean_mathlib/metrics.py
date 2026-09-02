from __future__ import annotations

import argparse
import gc
import json
import math
import tomllib
from typing import Any

import numpy as np
import polars as pl
import scipy.special
import scipy.stats

from knowledge_reuse.analysis.concentration import gini, hhi, top_share
from knowledge_reuse.analysis.powerlaw import fit_tail
from knowledge_reuse.sources.lean_mathlib.layout import (
    CONFIG_PATH,
    complexity_normalized_root,
    normalized_root,
    run_results_root,
)


CONFIG = tomllib.loads(CONFIG_PATH.read_text())

COMPLEXITY_METRICS = (
    "source_bytes",
    "source_lines",
    "source_tokens",
    "type_const_unique",
    "value_const_unique",
    "type_expr_unique_ptr_nodes",
    "type_expr_dag_arcs",
    "type_expr_max_depth",
    "type_expr_tree_occurrences",
    "type_expr_expansion_factor",
    "value_expr_unique_ptr_nodes",
    "value_expr_dag_arcs",
    "value_expr_max_depth",
    "value_expr_tree_occurrences",
    "value_expr_expansion_factor",
)

REGRESSION_METRICS = (
    "source_tokens",
    "type_const_unique",
    "type_expr_unique_ptr_nodes",
    "type_expr_dag_arcs",
    "type_expr_max_depth",
    "type_expr_tree_occurrences",
    "type_expr_expansion_factor",
    "value_const_unique",
    "value_expr_unique_ptr_nodes",
    "value_expr_dag_arcs",
    "value_expr_max_depth",
    "value_expr_tree_occurrences",
    "value_expr_expansion_factor",
)

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
    "multiplicity",
    "node_id",
    "node_name",
    "node_module",
    "node_domain",
    "node_kind",
    "has_value",
    "source_bytes",
    "type_expr_nodes",
    "value_expr_nodes",
    "type_expr_unique_ptr_nodes",
    "type_expr_dag_arcs",
    "type_expr_max_depth",
    "type_expr_tree_occurrences",
    "type_expr_expansion_factor",
    "value_expr_unique_ptr_nodes",
    "value_expr_dag_arcs",
    "value_expr_max_depth",
    "value_expr_tree_occurrences",
    "value_expr_expansion_factor",
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
            "Expr complexity",
            "high",
            "CategoryTheory.Limits.colimitLimitToLimitColimit_surjective",
            "固定 snapshot 候选；缺失时选择非生成节点中 value complexity 最大者",
            "真实高展开复杂度 theorem，用于比较 DAG 结构与展开树规模。",
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
                fallback = node_metrics.filter(pl.col("is_definition") & pl.col("has_value")).sort(
                    "type_expr_nodes", "name"
                )
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
                type_expr_unique_ptr_nodes=record.get("type_expr_unique_ptr_nodes"),
                type_expr_dag_arcs=record.get("type_expr_dag_arcs"),
                type_expr_max_depth=record.get("type_expr_max_depth"),
                type_expr_tree_occurrences=record.get("type_expr_tree_occurrences"),
                type_expr_expansion_factor=record.get("type_expr_expansion_factor"),
                value_expr_unique_ptr_nodes=record.get("value_expr_unique_ptr_nodes"),
                value_expr_dag_arcs=record.get("value_expr_dag_arcs"),
                value_expr_max_depth=record.get("value_expr_max_depth"),
                value_expr_tree_occurrences=record.get("value_expr_tree_occurrences"),
                value_expr_expansion_factor=record.get("value_expr_expansion_factor"),
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
        name for _, _, src_name, dst_name, _, _ in edge_candidates for name in (src_name, dst_name)
    } | {"DFunLike.coe"}
    node_by_name = {
        row["name"]: row
        for row in nodes.filter(pl.col("name").is_in(sorted(needed_names))).iter_rows(named=True)
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
                multiplicity=found["multiplicity"][0],
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
    incoming = (
        edges.filter(pl.col("dst_id") == reuse_target["node_id"])
        .sort("src_id", "edge_type")
        .head(5)
    )
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
                multiplicity=edge["multiplicity"],
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
    domain_pairs: pl.DataFrame,
    edges: pl.DataFrame,
    nodes: pl.DataFrame,
    snapshot: str,
) -> None:
    selected = pl.concat(
        [
            domain_pairs.filter(pl.col("src_domain") != pl.col("dst_domain"))
            .sort("src_domain", "dst_domain", "src_id", "dst_id")
            .head(2),
            domain_pairs.filter(pl.col("src_domain") == pl.col("dst_domain"))
            .sort("src_domain", "src_id", "dst_id")
            .head(1),
        ]
    )
    selected_ids = selected["src_id"].to_list() + selected["dst_id"].to_list()
    node_by_id = {
        row["node_id"]: row
        for row in nodes.filter(pl.col("node_id").is_in(selected_ids)).iter_rows(named=True)
    }
    for index, edge in enumerate(selected.iter_rows(named=True), 1):
        src, dst = node_by_id[edge["src_id"]], node_by_id[edge["dst_id"]]
        pair_edge_types = (
            edges.filter(
                (pl.col("src_id") == edge["src_id"]) & (pl.col("dst_id") == edge["dst_id"])
            )
            .sort("edge_type")["edge_type"]
            .to_list()
        )
        edge_type = "+".join(pair_edge_types)
        examples.append(
            _example_row(
                example_id=f"domain.edge.{index:02d}",
                concept="domain dependency matrix",
                role="cross_domain" if src["domain"] != dst["domain"] else "within_domain",
                selection_rule=(
                    "internal unique dependency pairs 按 src_domain、dst_domain、"
                    "src_id、dst_id 排序：前两条跨领域 pair 与第一条领域内 pair"
                ),
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
                edge_type=edge_type,
                evidence=(
                    f"normalized/edges.parquet#src_id={src['node_id']},dst_id={dst['node_id']}"
                ),
                source_locator=f"{src['source_file']}::{src['name']}",
                explanation=(
                    "该唯一 (src,dst) pair 使对应 src_domain→dst_domain matrix cell "
                    "增加 1；TYPE/VALUE 同时存在仍只增加 1。"
                ),
                caveat="单个 pair 只解释矩阵累加规则，不代表领域间总体强度。",
            )
        )


def with_node_metrics(nodes: pl.DataFrame, edges: pl.DataFrame) -> pl.DataFrame:
    internal_ids = nodes.select("node_id")
    internal_edges = edges.join(
        internal_ids.rename({"node_id": "dst_id"}), on="dst_id", how="inner"
    )
    reuse_edges = internal_edges.filter(pl.col("src_id") != pl.col("dst_id"))
    indegree = reuse_edges.group_by("dst_id").agg(
        pl.col("src_id").n_unique().alias("in_degree_all"),
        pl.col("src_id").filter(pl.col("edge_type") == "TYPE").n_unique().alias("in_degree_type"),
        pl.col("src_id").filter(pl.col("edge_type") == "VALUE").n_unique().alias("in_degree_value"),
        pl.col("multiplicity").sum().alias("in_occurrences_all"),
        pl.col("multiplicity")
        .filter(pl.col("edge_type") == "TYPE")
        .sum()
        .alias("in_occurrences_type"),
        pl.col("multiplicity")
        .filter(pl.col("edge_type") == "VALUE")
        .sum()
        .alias("in_occurrences_value"),
    )
    outdegree = edges.group_by("src_id").agg(
        pl.col("dst_id").n_unique().alias("out_degree_all"),
        pl.col("multiplicity").sum().alias("out_occurrences_all"),
    )
    return (
        nodes.join(indegree, left_on="node_id", right_on="dst_id", how="left")
        .join(outdegree, left_on="node_id", right_on="src_id", how="left")
        .with_columns(
            pl.col(column).fill_null(0).cast(pl.UInt64)
            for column in (
                "in_degree_all",
                "in_degree_type",
                "in_degree_value",
                "in_occurrences_all",
                "in_occurrences_type",
                "in_occurrences_value",
                "out_degree_all",
                "out_occurrences_all",
            )
        )
    )


def population_degrees(
    nodes: pl.DataFrame,
    edges: pl.DataFrame,
    node_metrics: pl.DataFrame,
    domain_pairs: pl.DataFrame,
) -> dict[str, np.ndarray]:
    node_kind = nodes.select("node_id", "kind")
    typed = edges.join(
        node_kind.rename({"node_id": "src_id", "kind": "src_kind"}), on="src_id", how="inner"
    ).join(
        node_kind.rename({"node_id": "dst_id", "kind": "dst_kind"}),
        on="dst_id",
        how="inner",
    ).filter(pl.col("src_id") != pl.col("dst_id"))

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
        "definition_to_definition": dst_degrees(
            typed.filter(
                pl.col("src_kind").is_in(["definition", "opaque"])
                & pl.col("dst_kind").is_in(["definition", "opaque"])
            )
        ),
    }
    for kind in sorted(nodes["kind"].unique().drop_nulls().to_list()):
        populations[f"kind:{kind}"] = node_metrics.filter(pl.col("kind") == kind)[
            "in_degree_all"
        ].to_numpy()
    domain_target_counts = domain_pairs.group_by("src_domain", "dst_id").agg(
        pl.col("src_id").n_unique().alias("degree")
    )
    for domain in sorted(nodes["domain"].unique().drop_nulls().to_list()):
        populations[f"domain:{domain}"] = domain_target_counts.filter(
            pl.col("src_domain") == domain
        )["degree"].to_numpy()
    return populations


def fit_rank_frequency(values: np.ndarray, population: str, xmin: float | None) -> dict[str, Any]:
    """Fit log C(r) = intercept - beta log r on the selected positive tail.

    ``beta`` is the rank--frequency exponent comparable to a Zipf ``1/r``
    slope.  It is deliberately kept separate from the probability-mass tail
    exponent returned by :func:`fit_tail`.
    """
    data = np.asarray(values, dtype=float)
    data = data[np.isfinite(data) & (data > 0)]
    result: dict[str, Any] = {
        "population": population,
        "positive_n": int(data.size),
        "xmin": xmin,
        "status": "insufficient_tail_observations",
    }
    if xmin is None:
        return result
    tail = np.sort(data[data >= xmin])[::-1]
    result["tail_n"] = int(tail.size)
    if tail.size < 20 or np.unique(tail).size < 3:
        return result
    ranks = np.arange(1, tail.size + 1, dtype=float)
    fitted = scipy.stats.linregress(np.log(ranks), np.log(tail))
    beta = float(-fitted.slope)
    result.update(
        {
            "status": "ok",
            "beta_rank": beta,
            "intercept": float(fitted.intercept),
            "r_squared": float(fitted.rvalue**2),
            "slope_std_error": float(fitted.stderr),
            "distance_from_zipf_1": abs(beta - 1.0),
        }
    )
    return result


def internal_unique_dependency_pairs(nodes: pl.DataFrame, edges: pl.DataFrame) -> pl.DataFrame:
    """Collapse TYPE/VALUE duplicates and attach source/target path domains."""
    node_domain = nodes.select("node_id", "domain")
    return (
        edges.filter(pl.col("src_id") != pl.col("dst_id"))
        .select("src_id", "dst_id")
        .unique()
        .join(
            node_domain.rename({"node_id": "src_id", "domain": "src_domain"}),
            on="src_id",
            how="inner",
        )
        .join(
            node_domain.rename({"node_id": "dst_id", "domain": "dst_domain"}),
            on="dst_id",
            how="inner",
        )
    )


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
    _, kind = np.unique(kind, return_inverse=True)
    _, domain = np.unique(domain, return_inverse=True)
    kind_count = int(kind.max()) + 1
    domain_count = int(domain.max()) + 1
    raw_length = frame[length_column].to_numpy().astype(float)
    length = np.log1p(raw_length)
    response = frame["in_degree_all"].to_numpy().astype(float)
    parameter_count = 2 + (kind_count - 1) + (domain_count - 1)

    def linear_predictor(params: np.ndarray) -> np.ndarray:
        kind_effect = np.concatenate(([0.0], params[2 : 1 + kind_count]))
        domain_effect = np.concatenate(([0.0], params[1 + kind_count :]))
        return params[0] + params[1] * length + kind_effect[kind] + domain_effect[domain]

    def objective(params: np.ndarray) -> tuple[float, np.ndarray]:
        eta = linear_predictor(params)
        # NB2 with fixed alpha=1 has log-likelihood, up to constants,
        # y*eta - (y+1)*log(1+exp(eta)).  logaddexp is overflow-safe.
        loss = float(np.sum((response + 1.0) * np.logaddexp(0.0, eta) - response * eta))
        score_eta = (response + 1.0) * scipy.special.expit(eta) - response
        gradient = np.empty(parameter_count, dtype=float)
        gradient[0] = score_eta.sum()
        gradient[1] = np.dot(score_eta, length)
        gradient[2 : 1 + kind_count] = np.bincount(kind, weights=score_eta, minlength=kind_count)[
            1:
        ]
        gradient[1 + kind_count :] = np.bincount(domain, weights=score_eta, minlength=domain_count)[
            1:
        ]
        return loss, gradient

    def fisher_information(weights: np.ndarray) -> np.ndarray:
        information = np.zeros((parameter_count, parameter_count), dtype=float)
        information[0, 0] = weights.sum()
        information[0, 1] = information[1, 0] = np.dot(weights, length)
        information[1, 1] = np.dot(weights, length * length)
        kind_w = np.bincount(kind, weights=weights, minlength=kind_count)[1:]
        kind_wx = np.bincount(kind, weights=weights * length, minlength=kind_count)[1:]
        domain_w = np.bincount(domain, weights=weights, minlength=domain_count)[1:]
        domain_wx = np.bincount(domain, weights=weights * length, minlength=domain_count)[1:]
        kind_slice = slice(2, 1 + kind_count)
        domain_slice = slice(1 + kind_count, parameter_count)
        information[0, kind_slice] = information[kind_slice, 0] = kind_w
        information[1, kind_slice] = information[kind_slice, 1] = kind_wx
        information[0, domain_slice] = information[domain_slice, 0] = domain_w
        information[1, domain_slice] = information[domain_slice, 1] = domain_wx
        information[kind_slice, kind_slice] = np.diag(kind_w)
        information[domain_slice, domain_slice] = np.diag(domain_w)
        cross = np.zeros((kind_count - 1, domain_count - 1), dtype=float)
        mask = (kind > 0) & (domain > 0)
        np.add.at(cross, (kind[mask] - 1, domain[mask] - 1), weights[mask])
        information[kind_slice, domain_slice] = cross
        information[domain_slice, kind_slice] = cross.T
        return information

    initial = np.zeros(parameter_count, dtype=float)
    initial[0] = math.log(max(response.mean(), 1e-6))
    try:
        params = initial
        loss, gradient = objective(params)
        converged = False
        iteration = 0
        for iteration in range(1, 61):
            eta = linear_predictor(params)
            mu = np.exp(np.clip(eta, -700, 700))
            information = fisher_information(mu / (1.0 + mu))
            ridge = max(float(np.trace(information)), 1.0) * 1e-12
            step = np.linalg.solve(information + np.eye(parameter_count) * ridge, -gradient)
            scale_factor = 1.0
            while scale_factor >= 2**-14:
                candidate = params + scale_factor * step
                candidate_loss, candidate_gradient = objective(candidate)
                if candidate_loss <= loss:
                    break
                scale_factor /= 2
            if scale_factor < 2**-14:
                break
            params = candidate
            relative_improvement = (loss - candidate_loss) / max(abs(loss), 1.0)
            loss, gradient = candidate_loss, candidate_gradient
            if np.max(np.abs(scale_factor * step)) < 1e-7 or relative_improvement < 1e-10:
                converged = True
                break
        eta = linear_predictor(params)
        mu = np.exp(np.clip(eta, -700, 700))
        weights = mu / (1.0 + mu)
        information = fisher_information(weights)
        model_covariance = np.linalg.pinv(information, hermitian=True)
        observation_score = (response + 1.0) * scipy.special.expit(eta) - response
        meat = fisher_information(observation_score * observation_score)
        robust_covariance = model_covariance @ meat @ model_covariance
        if frame.height > parameter_count:
            robust_covariance *= frame.height / (frame.height - parameter_count)
        model_std_error = math.sqrt(max(float(model_covariance[1, 1]), 0.0))
        std_error = math.sqrt(max(float(robust_covariance[1, 1]), 0.0))
        coefficient = float(params[1])
        z_score = coefficient / std_error if std_error else math.inf
        reference_value = float(np.median(raw_length))
        doubling_delta = math.log1p(2 * reference_value) - math.log1p(reference_value)
        pearson_variance = mu + np.square(mu)
        pearson_dispersion = float(
            np.sum(np.square(response - mu) / pearson_variance)
            / max(frame.height - parameter_count, 1)
        )
        result.update(
            {
                "status": "ok_nb2_fixed_dispersion" if converged else "not_converged",
                "coefficient": coefficient,
                "std_error": std_error,
                "model_std_error": model_std_error,
                "standard_error_type": "HC1_sandwich",
                "ci_low": coefficient - 1.96 * std_error,
                "ci_high": coefficient + 1.96 * std_error,
                "p_value": float(2 * scipy.stats.norm.sf(abs(z_score))),
                "alpha_dispersion": 1.0,
                "pearson_dispersion": pearson_dispersion,
                "effect_reference_value": reference_value,
                "doubling_effect_pct_at_reference": float(
                    (math.exp(coefficient * doubling_delta) - 1) * 100
                ),
                "controls": "kind+domain",
                "optimizer_iterations": iteration,
                "error": None if converged else "Fisher scoring did not converge",
            }
        )
    except (ValueError, np.linalg.LinAlgError) as error:
        result.update({"status": "failed", "error": str(error)})
    return result


def correlations(node_metrics: pl.DataFrame) -> list[dict[str, Any]]:
    rows = []
    for length in COMPLEXITY_METRICS:
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
    for length in COMPLEXITY_METRICS:
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
    complexity = pl.read_parquet(
        complexity_normalized_root(snapshot, run_kind) / "nodes.parquet"
    ).drop("snapshot_id", "module", "has_value")
    nodes = nodes.join(complexity, on="name", how="inner", validate="1:1").with_columns(
        (pl.col("type_expr_tree_occurrences") / pl.col("type_expr_unique_ptr_nodes")).alias(
            "type_expr_expansion_factor"
        ),
        (pl.col("value_expr_tree_occurrences") / pl.col("value_expr_unique_ptr_nodes")).alias(
            "value_expr_expansion_factor"
        ),
    )
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
        positive = values[values > 0]
        view_metrics.append(
            {
                "view": view,
                "nodes": frame.height,
                "positive_nodes": int(positive.size),
                "gini": gini(values),
                "hhi": hhi(values),
                "top_1pct_share": top_share(values, 0.01),
                "top_5pct_share": top_share(values, 0.05),
                "top_10pct_share": top_share(values, 0.10),
                "gini_positive": gini(positive),
                "top_1pct_share_positive": top_share(positive, 0.01),
                "top_5pct_share_positive": top_share(positive, 0.05),
                "top_10pct_share_positive": top_share(positive, 0.10),
            }
        )
    pl.DataFrame(view_metrics).write_parquet(
        metrics_dir / "view_metrics.parquet", compression="zstd"
    )

    # Fit the dense kind/domain regression design before materializing the
    # much larger source-domain dependency-pair table.
    regressions = pl.DataFrame(
        [fit_regression(node_metrics, length) for length in REGRESSION_METRICS]
    )
    regressions.write_parquet(metrics_dir / "regressions.parquet", compression="zstd")
    stratified_rows = []
    for stratum in ("theorem", "definition"):
        stratum_frame = node_metrics.filter(pl.col("kind") == stratum)
        for length in (
            "source_tokens",
            "type_expr_unique_ptr_nodes",
            "value_expr_unique_ptr_nodes",
            "value_expr_tree_occurrences",
        ):
            row = fit_regression(stratum_frame, length)
            row.update({"stratum": stratum, "controls": "domain (within kind)"})
            stratified_rows.append(row)
    pl.DataFrame(stratified_rows).write_parquet(
        metrics_dir / "stratified_regressions.parquet", compression="zstd"
    )
    correlation_rows = correlations(node_metrics)
    pl.DataFrame(correlation_rows).write_parquet(
        metrics_dir / "length_correlations.parquet", compression="zstd"
    )
    length_bins(node_metrics).write_parquet(
        metrics_dir / "length_binned.parquet", compression="zstd"
    )
    gc.collect()
    domain_pairs = internal_unique_dependency_pairs(nodes, edges)
    populations = population_degrees(nodes, edges, node_metrics, domain_pairs)
    fits = pl.DataFrame([fit_tail(values, name) for name, values in populations.items()])
    fits.write_parquet(metrics_dir / "powerlaw_fits.parquet", compression="zstd")
    fit_by_population = {row["population"]: row for row in fits.iter_rows(named=True)}
    rank_fits = pl.DataFrame(
        [
            fit_rank_frequency(
                values,
                name,
                fit_by_population[name].get("xmin"),
            )
            for name, values in populations.items()
        ]
    )
    rank_fits.write_parquet(metrics_dir / "rank_frequency_fits.parquet", compression="zstd")
    rank_by_population = {row["population"]: row for row in rank_fits.iter_rows(named=True)}
    kind_rows = []
    for kind in sorted(nodes["kind"].unique().drop_nulls().to_list()):
        values = node_metrics.filter(pl.col("kind") == kind)["in_degree_all"].to_numpy()
        positive = values[values > 0]
        population = f"kind:{kind}"
        fit_row = fit_by_population[population]
        rank_row = rank_by_population[population]
        kind_rows.append(
            {
                "kind": kind,
                "node_count": int(values.size),
                "positive_node_count": int(positive.size),
                "reuse_sum": int(values.sum()),
                "gini_all": gini(values),
                "gini_positive": gini(positive),
                "top_1pct_share_positive": top_share(positive, 0.01),
                "top_5pct_share_positive": top_share(positive, 0.05),
                "top_10pct_share_positive": top_share(positive, 0.10),
                "degree_tail_alpha": fit_row.get("alpha"),
                "xmin": fit_row.get("xmin"),
                "tail_n": fit_row.get("tail_n"),
                "rank_exponent_beta": rank_row.get("beta_rank"),
                "rank_r_squared": rank_row.get("r_squared"),
            }
        )
    pl.DataFrame(kind_rows).write_parquet(
        metrics_dir / "kind_reuse_metrics.parquet", compression="zstd"
    )
    availability = (
        node_metrics.group_by("kind")
        .agg(
            pl.len().alias("node_count"),
            pl.col("has_value").sum().alias("value_available_count"),
        )
        .with_columns(
            (pl.col("value_available_count") / pl.col("node_count")).alias(
                "value_available_fraction"
            ),
            (pl.col("node_count") - pl.col("value_available_count")).alias("value_null_count"),
        )
        .sort("node_count", descending=True)
    )
    availability.write_parquet(metrics_dir / "value_availability.parquet", compression="zstd")

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
    domain_reuse_matrix = (
        domain_pairs.group_by("src_domain", "dst_domain")
        .agg(pl.len().alias("dependency_pair_count"))
        .with_columns(
            (
                pl.col("dependency_pair_count")
                / pl.col("dependency_pair_count").sum().over("src_domain")
            ).alias("row_share")
        )
        .sort("src_domain", "dst_domain")
    )
    domain_reuse_matrix.write_parquet(
        tables_dir / "domain_reuse_matrix.parquet", compression="zstd"
    )
    append_domain_examples(report_examples, domain_pairs, edges, nodes, snapshot)
    pl.DataFrame(report_examples).select(EXAMPLE_COLUMNS).write_parquet(
        tables_dir / "report_examples.parquet", compression="zstd"
    )
    domain_rows = []
    target_domain_count = domain_pairs["dst_domain"].n_unique()
    for domain in sorted(nodes["domain"].unique().drop_nulls().to_list()):
        domain_nodes = node_metrics.filter(pl.col("domain") == domain)
        outbound = domain_reuse_matrix.filter(pl.col("src_domain") == domain)
        probabilities = outbound["row_share"].to_numpy()
        entropy = (
            float(-(probabilities * np.log(probabilities)).sum()) if probabilities.size else 0.0
        )
        normalized_entropy = (
            entropy / math.log(target_domain_count) if target_domain_count > 1 else 0.0
        )
        target_counts = (
            domain_pairs.filter(pl.col("src_domain") == domain)
            .group_by("dst_id")
            .agg(pl.col("src_id").n_unique().alias("degree"))
        )
        values = target_counts["degree"].to_numpy()
        fit_row = fits.filter(pl.col("population") == f"domain:{domain}")
        rank_row = rank_fits.filter(pl.col("population") == f"domain:{domain}")
        internal_count = outbound.filter(pl.col("src_domain") == pl.col("dst_domain"))[
            "dependency_pair_count"
        ].sum()
        total_outbound = outbound["dependency_pair_count"].sum()
        domain_rows.append(
            {
                "domain": domain,
                "node_count": domain_nodes.height,
                "reused_target_count": target_counts.height,
                "edge_count": int(total_outbound or 0),
                "gini": gini(values),
                "top_1pct_share": top_share(values, 0.01),
                "top_5pct_share": top_share(values, 0.05),
                "top_10pct_share": top_share(values, 0.10),
                "internal_dependency_share": (
                    float(internal_count / total_outbound) if total_outbound else 0.0
                ),
                "outbound_domain_diversity": outbound["dst_domain"].n_unique(),
                "reference_entropy_raw": entropy,
                "reference_entropy_proxy": normalized_entropy,
                "reference_entropy_target_domain_count": target_domain_count,
                "effective_target_domains": math.exp(entropy),
                "alpha": fit_row["alpha"][0] if fit_row.height else None,
                "xmin": fit_row["xmin"][0] if fit_row.height else None,
                "tail_n": fit_row["tail_n"][0] if fit_row.height else None,
                "rank_exponent_beta": (rank_row["beta_rank"][0] if rank_row.height else None),
                "rank_r_squared": (rank_row["r_squared"][0] if rank_row.height else None),
            }
        )
    domain_metrics = pl.DataFrame(domain_rows)
    domain_metrics.write_parquet(metrics_dir / "domain_metrics.parquet", compression="zstd")
    comparable_domains = domain_metrics.filter(pl.col("node_count") >= 100)
    domain_association_rows = []
    for left, right in (
        ("reference_entropy_proxy", "gini"),
        ("reference_entropy_proxy", "top_1pct_share"),
        ("reference_entropy_proxy", "rank_exponent_beta"),
        ("node_count", "gini"),
        ("node_count", "reference_entropy_proxy"),
    ):
        coefficient, p_value = scipy.stats.spearmanr(
            comparable_domains[left].to_numpy(),
            comparable_domains[right].to_numpy(),
        )
        domain_association_rows.append(
            {
                "left_metric": left,
                "right_metric": right,
                "n": comparable_domains.height,
                "spearman_rho": float(coefficient),
                "p_value": float(p_value),
            }
        )
    pl.DataFrame(domain_association_rows).write_parquet(
        metrics_dir / "domain_associations.parquet", compression="zstd"
    )

    del domain_pairs, internal_edges, populations
    gc.collect()

    top_reuse = node_metrics.sort("in_degree_all", "name", descending=[True, False]).head(100)
    top_reuse.write_csv(tables_dir / "top_reuse.csv")
    summary = {
        "schema_version": "analysis-summary-v1",
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "module_count": modules.height,
        "declaration_count": nodes.height,
        "declaration_counts_by_kind": dict(nodes.group_by("kind").len().sort("kind").iter_rows()),
        "edge_count": edges.height,
        "constant_occurrence_count": int(edges["multiplicity"].sum()),
        "all_unique_pair_count": edges.select("src_id", "dst_id").unique().height,
        "type_edge_count": edges.filter(pl.col("edge_type") == "TYPE").height,
        "value_edge_count": edges.filter(pl.col("edge_type") == "VALUE").height,
        "type_constant_occurrence_count": int(
            edges.filter(pl.col("edge_type") == "TYPE")["multiplicity"].sum()
        ),
        "value_constant_occurrence_count": int(
            edges.filter(pl.col("edge_type") == "VALUE")["multiplicity"].sum()
        ),
        "self_loop_count": edges.filter(pl.col("src_id") == pl.col("dst_id")).height,
        "self_loop_occurrence_count": int(
            edges.filter(pl.col("src_id") == pl.col("dst_id"))["multiplicity"].sum()
        ),
        "zero_indegree_fraction": float(np.count_nonzero(degree == 0) / degree.size),
        "zero_outdegree_fraction": float(
            np.count_nonzero(node_metrics["out_degree_all"].to_numpy() == 0) / nodes.height
        ),
        "isolated_fraction": float(
            np.count_nonzero((degree == 0) & (node_metrics["out_degree_all"].to_numpy() == 0))
            / nodes.height
        ),
        "reuse_concentration": view_metrics[0],
        "veldhuizen_reuse_concentration": {
            "population": "positive unique-consumer indegree targets",
            "nodes": view_metrics[0]["positive_nodes"],
            "gini": view_metrics[0]["gini_positive"],
            "top_1pct_share": view_metrics[0]["top_1pct_share_positive"],
            "top_5pct_share": view_metrics[0]["top_5pct_share_positive"],
            "top_10pct_share": view_metrics[0]["top_10pct_share_positive"],
        },
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
