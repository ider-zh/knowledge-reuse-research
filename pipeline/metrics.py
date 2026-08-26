from __future__ import annotations

import argparse
import json
import math
import pathlib
import tomllib
import warnings
from typing import Any

import numpy as np
import polars as pl
import scipy.stats
import statsmodels.api as sm

from pipeline.powerlaw import fit_tail


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG = tomllib.loads((ROOT / "configs" / "experiment-v1.toml").read_text())


def gini(values: np.ndarray) -> float:
    data = np.asarray(values, dtype=float)
    if data.size == 0 or data.sum() == 0:
        return 0.0
    data = np.sort(data)
    n = data.size
    return float((2 * np.dot(np.arange(1, n + 1), data) / (n * data.sum())) - (n + 1) / n)


def hhi(values: np.ndarray) -> float:
    total = np.asarray(values, dtype=float).sum()
    return float(np.square(values / total).sum()) if total else 0.0


def top_share(values: np.ndarray, fraction: float) -> float:
    data = np.asarray(values, dtype=float)
    if data.size == 0 or data.sum() == 0:
        return 0.0
    count = max(1, math.ceil(data.size * fraction))
    return float(np.sort(data)[-count:].sum() / data.sum())


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
    parquet_dir = ROOT / "data" / "parquet" / snapshot / run_kind
    metrics_dir = ROOT / "results" / "metrics"
    tables_dir = ROOT / "results" / "tables"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    tables_dir.mkdir(parents=True, exist_ok=True)
    nodes = pl.read_parquet(parquet_dir / "nodes.parquet")
    edges = pl.read_parquet(parquet_dir / "edges.parquet")
    modules = pl.read_parquet(parquet_dir / "modules.parquet")
    node_metrics = with_node_metrics(nodes, edges)
    node_metrics.write_parquet(metrics_dir / "node_metrics.parquet", compression="zstd")

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
    (ROOT / "results" / f"analysis-{run_kind}-summary.json").write_text(
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
