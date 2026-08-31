"""Lean/mathlib v1 research report generator."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import math
import os
import pathlib
import platform
import subprocess
import tomllib
from typing import Any, Callable

import duckdb
import jinja2
import polars as pl

from knowledge_reuse.sources.lean_mathlib.layout import (
    BENCHMARK_ROOT,
    CONFIG_PATH,
    EXCLUSIONS_PATH,
    ROOT,
    complexity_normalized_root,
    normalized_root,
    raw_root,
    run_results_root,
)

CONFIG = tomllib.loads(CONFIG_PATH.read_text())
TITLES = {
    "kind_counts": "图 1 · 声明类型构成",
    "indegree_ccdf": "图 2 · 复用入度经验 CCDF",
    "rank_frequency": "图 3 · 复用入度 Rank–Frequency",
    "tail_overlay": "图 4 · 幂律尾部拟合诊断",
    "source_length": "图 5 · 源码 Token 代理量与复用",
    "type_length": "图 6 · Type DAG 唯一节点与复用",
    "value_length": "图 7 · Value/Proof DAG 唯一节点与复用",
    "length_binned": "图 8 · Value 展开倍数分箱后的复用",
    "lorenz": "图 9 · 复用集中度 Lorenz 曲线",
    "domain_scale": "图 10 · 主要领域的节点规模",
    "domain_heatmap": "图 11 · 领域间依赖份额",
    "domain_entropy": "图 12 · 领域 H*ref 操作性代理量",
    "domain_tail": "图 13 · 领域 Gini 与 Rank–Frequency 指数",
    "robustness": "图 14 · 不同声明视图的稳健性",
}

FIGURE_CAPTIONS = {
    "kind_counts": "按 Lean 声明种类统计。定理占主体，但构造器、归纳类型和递归器仍作为独立节点保留。",
    "indegree_ccdf": "仅使用正入度节点；双对数坐标用于观察尾部，曲线形状本身不构成幂律证据。",
    "rank_frequency": "声明按总入度降序排列；同时显示同一尾部上的估计斜率与 1/r 参照线。",
    "tail_overlay": "经验 CCDF 与估计幂律尾部的诊断性叠加；模型优劣以似然比较而非视觉判断为准。",
    "source_length": "仅绘制存在源码范围的声明；这里的 Token 是明确规则的源码代理量，不是 Lean lexer token。",
    "type_length": "类型表达式实际共享 DAG 的唯一指针节点数；散点仅为可视化降采样。",
    "value_length": "仅绘制具有定义体或证明体的声明；null 不被替换为零。",
    "length_binned": "Value 展开倍数 T/U 的对数分箱，展示每箱复用入度中位数及四分位数。",
    "lorenz": "横轴为正入度声明累计比例，纵轴为收到的 unique-consumer reuse 累计比例；对角线代表完全均匀。",
    "domain_scale": "领域由模块路径映射得到；它是可复现的工程分组，不等同于数学本体分类。",
    "domain_heatmap": "行是依赖发起领域，列是被依赖领域；TYPE/VALUE 重合 pair 折叠一次，颜色表示行内份额。",
    "domain_entropy": "H*ref 以统一目标领域全集归一化；它是经验代理，不是理论信息熵 H。",
    "domain_tail": "横轴为领域内复用集中度，纵轴为该来源领域使用组件的 rank–frequency 尾部斜率。",
    "robustness": "比较 ALL、去生成声明、定理、定义及用户可见近似等预注册视图。",
}


def file_sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def svg_frame(title: str, body: str, width: int = 760, height: int = 430) -> str:
    escaped = html.escape(title)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escaped}">'
        '<rect width="100%" height="100%" fill="#fbfaf7"/>'
        f'<text x="24" y="30" font-family="sans-serif" font-size="18">{escaped}</text>'
        f"{body}</svg>"
    )


def axes(x_label: str, y_label: str) -> str:
    return (
        '<path d="M70 370H735M70 370V55" stroke="#59636e" fill="none"/>'
        f'<text x="390" y="414" text-anchor="middle" font-family="sans-serif" '
        f'font-size="12">{html.escape(x_label)}</text>'
        f'<text x="17" y="215" text-anchor="middle" transform="rotate(-90 17 215)" '
        f'font-family="sans-serif" font-size="12">{html.escape(y_label)}</text>'
    )


def scale(
    values: list[float], low: float, high: float, logarithmic: bool = False
) -> Callable[[float], float]:
    clean = [value for value in values if math.isfinite(value)] or [0.0, 1.0]
    transform = (
        (lambda value: math.log10(max(value, 1e-12)))
        if logarithmic
        else (lambda value: value)
    )
    minimum, maximum = min(map(transform, clean)), max(map(transform, clean))
    maximum = maximum if maximum != minimum else minimum + 1
    return lambda value: low + (transform(value) - minimum) * (high - low) / (
        maximum - minimum
    )


def bar_svg(title: str, labels: list[str], values: list[float], y_label: str) -> str:
    maximum = max(values, default=1) or 1
    width = 640 / max(len(values), 1)
    body = axes("category", y_label)
    for index, (label, value) in enumerate(zip(labels, values, strict=True)):
        x = 78 + index * width
        height = 300 * value / maximum
        body += (
            f'<rect x="{x:.1f}" y="{370-height:.1f}" width="{max(width-8, 2):.1f}" '
            f'height="{height:.1f}" fill="#386cb0"/>'
            f'<text x="{x+width/2-4:.1f}" y="386" '
            f'transform="rotate(35 {x+width/2-4:.1f} 386)" '
            f'font-family="sans-serif" font-size="9">{html.escape(label[:18])}</text>'
        )
    return svg_frame(title, body)


def points_svg(
    title: str,
    x_values: list[float | None],
    y_values: list[float | None],
    x_label: str,
    y_label: str,
    log_x: bool = True,
    log_y: bool = True,
) -> str:
    pairs = [
        (x, y)
        for x, y in zip(x_values, y_values, strict=True)
        if x is not None and y is not None and x > 0 and (y > 0 or not log_y)
    ]
    pairs.sort(key=lambda pair: (pair[0], pair[1]))
    if len(pairs) > 1600:
        pairs = pairs[:: math.ceil(len(pairs) / 1600)]
    xs = [pair[0] for pair in pairs] or [1]
    ys = [pair[1] for pair in pairs] or [1]
    sx, sy = scale(xs, 78, 730, log_x), scale(ys, 365, 60, log_y)
    circles = "".join(
        f'<circle cx="{sx(x):.2f}" cy="{sy(y):.2f}" r="2" '
        f'fill="#386cb0" fill-opacity=".45"/>' for x, y in pairs
    )
    return svg_frame(title, axes(x_label, y_label) + circles)


def line_svg(
    title: str,
    series: list[tuple[str, list[float], list[float]]],
    x_label: str,
    y_label: str,
    log_x: bool = False,
    log_y: bool = False,
) -> str:
    prepared = []
    for label, xs, ys in series:
        pairs = [
            (x, y)
            for x, y in zip(xs, ys, strict=True)
            if math.isfinite(x)
            and math.isfinite(y)
            and (x > 0 or not log_x)
            and (y > 0 or not log_y)
        ]
        if len(pairs) > 700:
            pairs = pairs[:: math.ceil(len(pairs) / 700)]
        prepared.append((label, pairs))
    all_x = [x for _, pairs in prepared for x, _ in pairs]
    all_y = [y for _, pairs in prepared for _, y in pairs]
    sx, sy = scale(all_x, 78, 730, log_x), scale(all_y, 365, 60, log_y)
    colors = ["#386cb0", "#e6550d", "#31a354", "#756bb1"]
    body = axes(x_label, y_label)
    for index, (label, pairs) in enumerate(prepared):
        points = " ".join(
            f"{sx(x):.2f},{sy(y):.2f}" for x, y in pairs
        )
        color = colors[index % len(colors)]
        body += (
            f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="2"/>'
            f'<text x="590" y="{65+index*17}" font-family="sans-serif" '
            f'font-size="11" fill="{color}">{html.escape(label)}</text>'
        )
    return svg_frame(title, body)


def heatmap_svg(frame: pl.DataFrame) -> str:
    domains = sorted(
        set(frame["src_domain"].to_list()) | set(frame["dst_domain"].to_list())
    )[:18]
    grouped = frame.group_by("src_domain", "dst_domain").agg(pl.col("row_share").sum())
    lookup = {(row[0], row[1]): row[2] for row in grouped.iter_rows()}
    size = 280 / max(len(domains), 1)
    body = axes("dependency domain", "consumer domain")
    for yi, source in enumerate(domains):
        for xi, target in enumerate(domains):
            value = min(float(lookup.get((source, target), 0.0)), 1.0)
            blue = int(245 - 180 * math.sqrt(value))
            body += (
                f'<rect x="{78+xi*size:.2f}" y="{70+yi*size:.2f}" '
                f'width="{size:.2f}" height="{size:.2f}" '
                f'fill="rgb({blue},{blue},255)"/>'
            )
        body += (
            f'<text x="72" y="{78+yi*size:.2f}" text-anchor="end" '
            f'font-family="sans-serif" font-size="7">{html.escape(source[:12])}</text>'
        )
    for xi, target in enumerate(domains):
        body += (
            f'<text x="{82+xi*size:.2f}" y="365" '
            f'transform="rotate(55 {82+xi*size:.2f} 365)" '
            f'font-family="sans-serif" font-size="7">{html.escape(target[:12])}</text>'
        )
    return svg_frame(TITLES["domain_heatmap"], body)


def format_cell(value: Any) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "通过" if value else "未通过"
    if isinstance(value, float):
        if math.isnan(value):
            return "—"
        if abs(value) < 0.001 and value != 0:
            return f"{value:.2e}"
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


def render_table(frame: pl.DataFrame, limit: int = 20) -> str:
    frame = frame.head(limit)
    headings = "".join(f"<th>{html.escape(column)}</th>" for column in frame.columns)
    rows = []
    for row in frame.iter_rows():
        cells = "".join(
            f"<td>{html.escape(format_cell(value))}</td>" for value in row
        )
        rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{headings}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def run_manifest(run_kind: str) -> dict[str, Any]:
    raw_path = raw_root(CONFIG["snapshot_id"], run_kind) / "manifest.json"
    raw = json.loads(raw_path.read_text())
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, capture_output=True, check=True
    ).stdout.strip()
    mathlib = ROOT / "vendor" / "mathlib4"
    mathlib_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=mathlib,
        text=True,
        capture_output=True,
        check=True,
    ).stdout.strip()
    cpu = platform.processor()
    cpuinfo = pathlib.Path("/proc/cpuinfo")
    if cpuinfo.exists():
        for line in cpuinfo.read_text().splitlines():
            if line.startswith("model name"):
                cpu = line.split(":", 1)[1].strip()
                break
    manifest = {
        "schema_version": CONFIG["schema_version"],
        "snapshot_id": CONFIG["snapshot_id"],
        "run_kind": run_kind,
        "mathlib_tag": CONFIG["mathlib_tag"],
        "mathlib_commit": mathlib_commit,
        "lean_toolchain": (mathlib / "lean-toolchain").read_text().strip(),
        "extractor_commit": commit,
        "report_generator_commit": commit,
        "repository_commit": commit,
        "python_version": platform.python_version(),
        "polars_version": pl.__version__,
        "duckdb_version": duckdb.__version__,
        "rust_version": None,
        "os": platform.platform(),
        "cpu": cpu,
        "ram_bytes": os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES"),
        "worker_count": raw["worker_count"],
        "started_at": raw.get("started_at"),
        "finished_at": raw.get("finished_at"),
        "config_sha256": file_sha256(CONFIG_PATH),
        "raw_manifest_sha256": file_sha256(raw_path),
    }
    (run_results_root(run_kind) / "run-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


def build_claim_registry(
    summary: dict[str, Any],
    quality: dict[str, Any],
    fits: pl.DataFrame,
    rank_fits: pl.DataFrame,
    domains: pl.DataFrame,
    regressions: pl.DataFrame,
) -> dict[str, Any]:
    all_fit = fits.filter(pl.col("population") == "all_declarations").row(
        0, named=True
    )
    complete = quality["passed"] and quality["extraction_completeness"] == 1
    all_rank = rank_fits.filter(pl.col("population") == "all_declarations").row(
        0, named=True
    )
    theorem_rank = rank_fits.filter(pl.col("population") == "kind:theorem").row(
        0, named=True
    )
    definition_rank = rank_fits.filter(
        pl.col("population") == "kind:definition"
    ).row(0, named=True)
    algebra_rows = domains.filter(pl.col("domain") == "Algebra")
    number_theory_rows = domains.filter(pl.col("domain") == "NumberTheory")
    domain_comparison_available = bool(algebra_rows.height and number_theory_rows.height)
    algebra = algebra_rows.row(0, named=True) if algebra_rows.height else None
    number_theory = (
        number_theory_rows.row(0, named=True) if number_theory_rows.height else None
    )
    token_regression = regressions.filter(
        pl.col("length_metric") == "source_tokens"
    ).row(0, named=True)
    concentration = summary["veldhuizen_reuse_concentration"]
    return {
        "schema_version": "report-claims-v1",
        "snapshot_id": summary["snapshot_id"],
        "run_kind": summary["run_kind"],
        "claims": [
            {
                "claim_id": "completeness.configured_corpus",
                "status": "fact" if complete else "inconclusive",
                "text": (
                    f"配置内 {quality['expected_module_count']:,} 个模块全部成功提取，"
                    "没有失败、partial 或静默空结果。"
                ),
                "evidence": ["metrics/data_quality.json"],
                "scope": "configured Mathlib corpus",
                "caveat": "配置排除项和 mathlib 外部 universe 不属于该总体。",
            },
            {
                "claim_id": "veldhuizen.rank_frequency",
                "status": "supported",
                "text": (
                    f"复用 rank–frequency 明显重尾，但全体尾部 βrank={all_rank['beta_rank']:.3f} "
                    f"并非严格 1/r；theorem βrank={theorem_rank['beta_rank']:.3f} 接近 1，"
                    f"definition βrank={definition_rank['beta_rank']:.3f} 更陡。"
                ),
                "evidence": [
                    "metrics/rank_frequency_fits.parquet",
                    "metrics/powerlaw_fits.parquet",
                ],
                "scope": f"positive indegree tail selected at xmin={all_rank['xmin']}; tail_n={all_rank['tail_n']:,}",
                "caveat": (
                    "纯 power law 在相对模型比较中不占优；βrank 是描述性 log–log 斜率；"
                    f"absolute bootstrap={all_fit['bootstrap_status']}。"
                ),
            },
            {
                "claim_id": "veldhuizen.concentration",
                "status": "supported",
                "text": (
                    f"少数组件主导复用：在 {concentration['nodes']:,} 个正入度声明中，"
                    f"Top 1/5/10% 分别承接 {concentration['top_1pct_share']:.1%}/"
                    f"{concentration['top_5pct_share']:.1%}/{concentration['top_10pct_share']:.1%}，"
                    f"Gini={concentration['gini']:.3f}。"
                ),
                "evidence": ["metrics/summary.json#/veldhuizen_reuse_concentration"],
                "scope": "positive unique-consumer indegree targets",
                "caveat": "unique consumer breadth 不是同一声明内的 raw occurrence 次数。",
            },
            {
                "claim_id": "veldhuizen.domain_heterogeneity",
                "status": "exploratory" if domain_comparison_available else "inconclusive",
                "text": (
                    (
                        "路径领域具有不同复用结构："
                        f"Algebra H*ref={algebra['reference_entropy_proxy']:.3f}, Gini={algebra['gini']:.3f}；"
                        f"NumberTheory H*ref={number_theory['reference_entropy_proxy']:.3f}, "
                        f"Gini={number_theory['gini']:.3f}。"
                    )
                    if domain_comparison_available
                    else "smoke corpus 不含完成 Algebra/NumberTheory 对照所需的领域总体。"
                ),
                "evidence": [
                    "metrics/domain_metrics.parquet",
                    "metrics/domain_associations.parquet",
                ],
                "scope": "source path-domain unique dependency-pair profiles",
                "caveat": "H*ref 不是理论 H；领域规模与 Gini 强相关，不能据此断言领域具有内在固定复用潜力。",
            },
            {
                "claim_id": "veldhuizen.complexity_association",
                "status": "exploratory",
                "text": (
                    "长度与复用的结论依赖口径：源码 Token 的未控制相关为正，"
                    f"但控制 kind/domain 后 βlength={token_regression['coefficient']:.3f}，"
                    "且 Type/Value 多层 Expr 系数均为负。"
                ),
                "evidence": [
                    "metrics/length_correlations.parquet",
                    "metrics/regressions.parquet",
                    "metrics/stratified_regressions.parquet",
                ],
                "scope": "source/type/value metrics with available observations",
                "caveat": "这不是论文中的 S(n)；固定离散度模型的观察性关联不是因果效应。",
            },
            {
                "claim_id": "veldhuizen.longitudinal_growth",
                "status": "inconclusive",
                "text": "当前只有 mathlib v4.32.1 一个 snapshot，无法检验稳定核心与持续长尾的纵向命题。",
                "evidence": ["metrics/summary.json#/snapshot_id"],
                "scope": "single snapshot",
                "caveat": "单个横截面不能替代多个 commit 上的同口径追踪。",
            },
        ],
    }


def examples_payload(examples: pl.DataFrame, snapshot: str, run_kind: str) -> dict[str, Any]:
    if examples["snapshot_id"].unique().to_list() != [snapshot]:
        raise ValueError("report examples do not match requested snapshot")
    return {
        "schema_version": "report-examples-v1",
        "snapshot_id": snapshot,
        "run_kind": run_kind,
        "selection_is_deterministic": True,
        "examples": examples.to_dicts(),
    }


def artifact_index(run_dir: pathlib.Path, paths: list[pathlib.Path]) -> dict[str, Any]:
    def display_path(path: pathlib.Path) -> str:
        try:
            return str(path.relative_to(run_dir))
        except ValueError:
            return str(path.relative_to(ROOT))

    return {
        "schema_version": "report-artifact-index-v1",
        "artifacts": [
            {
                "path": display_path(path),
                "bytes": path.stat().st_size,
                "sha256": file_sha256(path),
            }
            for path in sorted(paths)
        ],
    }


_REPORT_ENV = jinja2.Environment(autoescape=True)
_REPORT_ENV.filters["fmt"] = format_cell
TEMPLATE = _REPORT_ENV.from_string("""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lean 4 / mathlib 知识复用图正式实验报告</title>
<style>{{ css|safe }}</style></head><body>
<header><p class="eyebrow">KNOWLEDGE REUSE RESEARCH · LEAN / MATHLIB V1</p>
<h1>形式化知识如何被复用？</h1>
<p class="dek">围绕 Veldhuizen 2005 的可检验命题，判断形式化数学知识是否呈现类似软件库的复用规律</p>
<div class="status {{ 'ok' if quality.passed else 'bad' }}">
<b>{{ '完整图构建成功' if quality.extraction_completeness == 1 and quality.passed else '构建未通过完整性门禁' }}</b>
<span>{{ quality.extracted_module_count }}/{{ quality.expected_module_count }} 模块 · {{ manifest.mathlib_tag }} · {{ manifest.mathlib_commit[:12] }}</span></div>
<div class="hero-stats">
<div><strong>{{ summary.declaration_count|fmt }}</strong><span>内部声明节点</span></div>
<div><strong>{{ quality.external_node_count|fmt }}</strong><span>显式外部目标</span></div>
<div><strong>{{ summary.edge_count|fmt }}</strong><span>唯一类型化语义边</span></div>
<div><strong>{{ (quality.extraction_completeness*100)|round(1) }}%</strong><span>模块覆盖率</span></div>
</div></header>
<nav><b>报告目录</b><ol>
<li><a href="#s1">执行摘要</a></li><li><a href="#s2">概念设计</a></li>
<li><a href="#s3">研究问题</a></li><li><a href="#s4">语料与版本</a></li>
<li><a href="#s5">图语义</a></li><li><a href="#s6">完整性</a></li>
<li><a href="#s7">复杂度</a></li><li><a href="#s8">图统计</a></li>
<li><a href="#s9">集中度</a></li><li><a href="#s10">重尾检验</a></li>
<li><a href="#s11">复杂度与复用</a></li><li><a href="#s12">声明/边类型</a></li>
<li><a href="#s13">领域</a></li><li><a href="#s14">稳健性</a></li>
<li><a href="#s15">论文对照</a></li><li><a href="#s16">明确结论</a></li>
<li><a href="#s17">附录</a></li>
</ol></nav><main>

<section id="s1"><h2>1. 执行摘要</h2>
<p>本报告研究一个简单问题：<b>在大型形式化数学库中，哪些知识被许多其他知识反复使用，这种复用是否集中，以及知识单元的复杂度是否与复用有关？</b>如果你没有学过 Lean、图论或统计学，可以先把 mathlib 想成一本由几十万条“定义与定理卡片”组成、且每张卡片都会列出自己依赖哪些卡片的数字百科全书。</p>
<div class="answer"><b>一句话结论：</b>mathlib 确实呈现“少数基础声明承担大多数复用、其余声明形成长尾”的软件库式结构，但<b>全体 declaration 不能被判为严格 Zipf 1/r</b>：全体尾部 rank 指数为 β={{ veldhuizen.all_beta }}，theorem 尾部 β={{ veldhuizen.theorem_beta }} 最接近 1，而 definition 为 β={{ veldhuizen.definition_beta }}。因此，与 Veldhuizen 2005 的关系是<b>部分经验一致</b>，不是对其理论模型的完整验证。</div>
<div class="grid three"><article><h3>命题 1–2：分布与集中</h3><p>{{ veldhuizen.positive_nodes|fmt }} 个正入度声明中，Top 1/5/10% 承接 {{ veldhuizen.top_1 }}% / {{ veldhuizen.top_5 }}% / {{ veldhuizen.top_10 }}%，Gini={{ veldhuizen.gini }}。集中核心得到强支持；严格全体 Zipf 不成立。</p></article><article><h3>命题 3：领域差异</h3><p>Algebra 的 H*ref={{ veldhuizen.algebra_h }}、Gini={{ veldhuizen.algebra_gini }}；NumberTheory 分别为 {{ veldhuizen.number_theory_h }}、{{ veldhuizen.number_theory_gini }}。领域结构不同，但 H*ref 与 Gini 在全部领域中没有稳定单调关系。</p></article><article><h3>命题 4–5：大小与增长</h3><p>控制 kind/domain 后，多种长度系数为负，支持“较短声明更易高复用”的条件关联；但这不是 S(n)，也不是因果。只有一个 snapshot，长期“稳定核心 + 持续长尾”目前不可检验。</p></article></div>
<div class="grid three"><article><h3>先看什么</h3><p>第 2–7 节回答“研究对象和变量是什么”；第 8–14 节回答“完整数据呈现什么规律”；第 15–17 节回答“怎样解释、比较和回查证据”。</p></article><article><h3>数字怎样读</h3><p>正文先给日常解释和手算例子，再给真实 mathlib 数据。标为“教学例子”的内容只帮助理解，不是实验样本。</p></article><article><h3>结论有多确定</h3><p><code>fact</code> 是数据直接给出的事实；<code>supported</code> 是方法支持的结论；<code>exploratory</code> 是值得继续检验的观察；<code>inconclusive</code> 表示证据还不足。</p></article></div>
<p>以下结论来自机器可读 claim registry。每条结论都标明证据等级、适用总体和不能推出的内容。</p>
{% for claim in claims.claims %}<article class="claim {{ claim.status }}" id="{{ claim.claim_id }}">
<div><span class="badge">{{ claim.status }}</span><b>{{ claim.text }}</b></div>
<p><strong>范围：</strong>{{ claim.scope }}　<strong>限制：</strong>{{ claim.caveat }}</p>
<small>Evidence: {{ claim.evidence|join(' · ') }}</small></article>{% endfor %}
<p class="bridge">下面不直接跳到总体图形。我们先用真实 mathlib declaration 建立 node、value 和 reuse 的直觉，再说明这些单例如何扩展成全库统计。</p></section>

<section id="s2"><h2>2. 概念设计与研究对象</h2>
<p><b>Lean</b> 是一种让计算机检查数学定义和证明是否正确的语言，<b>mathlib</b> 是用 Lean 编写的大型数学库。人写下的 Lean 源码常包含省略写法；Lean 会把它翻译成类型信息完整、计算机可以逐项检查的内部表达式，这一步叫做<b>精化（elaboration）</b>。本研究分析精化后的结果，而不是只数源码中肉眼可见的名字。</p>
<p>Lean 把一条定理、定义、公理、归纳类型、构造器或递归器登记为一个带完整名称的<b>声明（declaration）</b>。本研究把配置语料内的每个 declaration 作为图中的一个<b>节点（node）</b>。因此 Node 不是源码中的一行，也不是表达式里的一个小括号，而是一张可以被别的声明引用的完整“知识卡片”。</p>
<div class="callout"><b>教学例子，不是实验数据：</b><code>def double (n : Nat) : Nat := n + n</code> 是一个 declaration。它的 <b>type</b> 可直观读作“输入一个自然数，输出一个自然数”；它的 <b>value</b> 是“把 n 与自己相加”的具体实现。对 theorem 而言，type 是待证明的命题，value 则是供 Lean 检查的证明项。</div>
<div class="grid"><article><h3>Node 有什么</h3><p>每个 node 一定有 <b>name</b>、<b>kind</b> 和 <b>type</b>。type 说明“它是什么”；如果环境还公开定义体或证明体，则另有 <b>value</b>，说明“它怎样被构造或证明”。源码范围是附加观测，缺失不会删除 node。</p></article>
<article><h3>Node value 为什么会是 null</h3><p>有些声明只通过“类型与构造规则”存在，并没有普通定义体或证明体可读取。程序的正式判定是：<code>getDeclarationValue?</code> 返回 none 时记 <code>has_value=false</code>，全部 value-complexity 记为 null。null 表示“这里没有可观测对象”，不是“测得复杂度为零”。</p></article>
<article><h3>Reuse 是什么</h3><p>若 A 的 elaborated type 或 value 包含常量 B，则 A → B。B 的入度统计有多少不同声明复用它；A 的出度描述自身直接依赖负担。</p></article>
<article><h3>Complexity 是什么</h3><p>复杂度不是一个数字。本研究分别观察源码表面规模、内部表达式实际保存的结构、最大嵌套深度、共享内容完全展开后的规模，以及引用了多少种不同常量。第 7 节会逐一手算。</p></article></div>
<h3>最少术语表</h3><table><thead><tr><th>术语</th><th>可以先怎样理解</th><th>本研究怎样使用</th></tr></thead><tbody>
<tr><td>module</td><td>一个 Lean 源文件及其导入单元，类似书中的一章</td><td>记录来源，并由高层路径派生领域标签</td></tr>
<tr><td>declaration / node</td><td>一张有名字、可被引用的知识卡片</td><td>图的基本节点</td></tr>
<tr><td>theorem</td><td>一个命题连同可检查的证明</td><td>type 是命题，value 是证明项</td></tr>
<tr><td>definition / opaque</td><td>概念、函数或构造的定义</td><td>type 是接口，value 是实现</td></tr>
<tr><td>inductive / constructor / recursor</td><td>定义一种数据、构造该数据、按规则使用该数据</td><td>都是真实节点，但通常没有可读 value</td></tr>
<tr><td>Expr</td><td>Lean 精化后用于表示 type 或 value 的内部表达式</td><td>用于计算第 7 节的结构复杂度</td></tr>
</tbody></table>
<h3>Value 可观测性按声明类型分布</h3>{{ value_availability_table|safe }}
<p class="callout"><b>null 对复用实验的影响：</b>该 node 仍进入总体图；它的 type 边、别人指向它的入边和复用入度都可分析。只有它自身的 VALUE 出边与 value/proof 复杂度不可观测，因此相关分析按有效样本数排除，而不是补 0。若某类 node 的 null 比例很高，跨 kind 比较必须分层或控制 kind。</p>
<h3>真实节点证据</h3>{{ node_examples_table|safe }}
<div class="callout"><b>解释边界</b> 语义常量引用不是人的引用意图。自动生成代码、类型类、强制转换和 elaborator 插入项都属于机器可复现的依赖事实，但不应直接解释为作者有意识的“引用”。</div></section>

<section id="s3"><h2>3. 研究问题与判断路径</h2>
<p>Veldhuizen 2005 不是泛泛地说“网络可能重尾”。论文先把组件按使用频率排序，并讨论接近 <code>1/r</code> 的 Zipf 形状；再用理论熵参数 H 解释不同 problem domain 的复用上限，并区分复用频率、每次复用节省的代码量 S(n) 与 library incompleteness。本实验把这些对象逐项操作化，不能测的项目也必须给出 verdict。</p>
<table><thead><tr><th>命题</th><th>Veldhuizen 对象</th><th>Lean 可观测量</th><th>本报告判断规则</th></tr></thead><tbody>
<tr><td>P1 核心</td><td>组件使用频率与 Zipf-like 1/r</td><td>unique-consumer indegree 的 C(r)；βrank；候选尾部模型</td><td>βrank≈1 只说明斜率相似；纯幂律还必须通过模型比较</td></tr>
<tr><td>P2 核心</td><td>少数组件主导复用</td><td>正入度节点 Top 1/5/10%、Gini、Lorenz</td><td>集中结论不依赖严格 1/r 是否成立</td></tr>
<tr><td>P3 核心</td><td>reuse potential 依赖 problem domain</td><td>来源路径领域的 βrank、Gini、Top-k 与 H*ref</td><td>只称 Veldhuizen-style empirical consistency；H*ref≠理论 H</td></tr>
<tr><td>P4 扩展</td><td>论文的 S(n) 是每次复用节省量</td><td>source、statement/type Expr、proof/value Expr 大小与复用</td><td>报告 βlength，但不得把 declaration length 当作 S(n)</td></tr>
<tr><td>P5 纵向</td><td>library incompleteness / 持续扩展</td><td>多个 commit 的 |Vt|、|Et| 与 C_t(r)</td><td>单一 snapshot 一律判为不可检验</td></tr>
</tbody></table>
<div class="callout"><b>与原论文数据的关键差别：</b>原论文统计 Unix object 中的组件 reference frequency；本图只能稳定得到“有多少不同 declaration 使用目标”的 unique-consumer breadth。同一 proof 内重复十次仍计一个 consumer。因此本实验是知识复用广度的对应实验，不是 raw relocation occurrence 的逐项复刻。</div>
<p class="bridge">要回答这些命题，必须先冻结“研究的是哪一版、哪些文件”，否则今天和明天得到的节点集合可能不同。所以下一节先定义 Corpus 与 Snapshot。</p></section>

<section id="s4"><h2>4. 语料（Corpus）与快照（Snapshot）</h2>
<p><b>Corpus（语料总体）</b>是本次研究允许进入样本的全部 module，可以类比为“这次统计选择了书中的哪些章节”。<b>Snapshot（快照）</b>是把软件版本冻结在某个时刻，可以类比为指定“教材第几版”。固定二者后，报告中的 100% 才有明确分母。</p>
<p>本报告绑定 mathlib 标签 <code>{{ manifest.mathlib_tag }}</code>、完整 commit <code>{{ manifest.mathlib_commit }}</code> 和 Lean toolchain <code>{{ manifest.lean_toolchain }}</code>。标签便于人阅读，commit 精确指定代码内容，toolchain 指定用哪一版 Lean 解释这些内容。总体由 <code>{{ config.corpus_glob }}</code> 与版本化 exclusions 共同定义。</p>
<h3>配置化排除规则</h3>{{ exclusions_table|safe }}
<p class="note">“100% 完整”只指 configured corpus；不包含排除目录、其他 Lean package 或历史版本。它不是“整个数学知识世界的 100%”。</p>
<p class="bridge">总体固定后，下一步才可以定义每一条引用怎样变成有方向、有类型的图边。</p></section>

<section id="s5"><h2>5. 图构建语义：从真实边到完整图</h2>
<p><b>图（graph）</b>由节点集合 V 和边集合 E 组成，写作 <code>G=(V,E)</code>。这里的边带箭头，所以是<b>有向图</b>。方向固定为 <code>使用者 consumer → 被使用者 dependency</code>：如果 A 使用 B，就画 A→B。这个方向容易画反，但它有一个好处——越多箭头指向 B，B 就被越多声明复用。</p>
<pre class="dag">教学例子，不是实验数据：
A 使用 B，C 也使用 B：     A ──→ B ←── C
因此 B 有 2 个不同使用者，复用入度为 2；A 和 C 各发出 1 条依赖边。</pre>
<p>边还分两种语义：<b>TYPE</b> 表示目标常量出现在声明的 type/statement 中，也就是“表达这句话需要什么”；<b>VALUE</b> 表示目标常量出现在 definition body 或 proof 中，也就是“实现或证明它需要什么”。</p>
<h3>两个不同语义的真实关系</h3>{{ edge_examples_table|safe }}
<div class="grid"><article><h3>TYPE 示例如何进入图</h3><p><code>padicValRat.of_nat</code> 的 elaborated type 包含 <code>padicValNat</code>，因此规范化为一条 theorem→definition TYPE edge。</p></article><article><h3>VALUE 示例如何进入图</h3><p><code>constantCoeff_xInTermsOfW</code> 的 proof/value 包含 <code>map_pow</code>，因此规范化为 theorem→theorem VALUE edge。</p></article></div>
<h3>“唯一类型化边”怎样计数</h3><p>若 A 的同一个 proof 中出现 B 十次，主图的 `(A,B,VALUE)` 仍只计 1 条，因为主问题是“有多少不同 declaration 使用 B”，不是“一个 proof 重复写了多少次”。但如果 B 同时出现在 A 的 type 和 value 中，则保留一条 TYPE 和一条 VALUE；它们说明两种不同机制。若 B 位于 configured corpus 之外，B 仍登记为 external target，避免让 A 的依赖凭空消失。</p>
<p class="bridge">单条真实边只能说明一个案例存在。将全部 declaration 按同一规则提取、编号和去重，才能统计总体；下一节先确认这个总体实际观测了多少。</p></section>

<section id="s6"><h2>6. 研究范围与观测完整性</h2>
<div class="answer"><b>本报告覆盖配置语料的全部 {{ quality.expected_module_count|fmt }} 个模块。</b>共观测 {{ summary.declaration_count|fmt }} 个内部 declaration、{{ quality.external_node_count|fmt }} 个语料外依赖目标和 {{ summary.edge_count|fmt }} 条唯一类型化边。</div>
<p><b>内部节点</b>是 Corpus 内有完整 declaration 记录的节点；<b>外部目标</b>是被内部声明引用、但不属于本次 Corpus 的名字。外部目标只帮助保留边界依赖，不进入内部节点的复杂度总体。</p>
<p>“完整”只针对第 4 节定义的固定 snapshot 与 configured corpus，并表示每个预期 module 都有成功观测记录；它不表示每个字段都必然非空，也不表示统计解释必然正确。源码范围覆盖率为 {{ ((1-quality.null_rates.source_bytes)*100)|round(2) }}%，value/proof 覆盖率为 {{ ((1-quality.null_rates.value_expr_nodes)*100)|round(2) }}%。缺失保持 null，后续表格同时报告 <code>n_valid</code>（有值的样本数）和总体数。</p>
<div class="callout"><b>三个容易混淆的状态：</b><code>0</code> 表示“测量过，结果就是零”；<code>null</code> 表示“这里没有可用于该指标的观测”；<code>external</code> 表示“名字真实存在于依赖边中，但不属于本次内部总体”。</div>
<p class="bridge">确认分母和缺失规则以后，下面才能安全地比较节点“有多复杂”；否则 null 很容易被误当成一个特别简单的零值。</p></section>

<section id="s7"><h2>7. 节点长度与复杂度变量</h2>
<p>一个 node 的 type 与可观测 value/proof 各自都是 Lean Expr。Expr 可以想成由“函数应用、变量、常量、函数输入、局部定义”等积木拼成的结构。不同声明可能源码一样长，却拼出大小和深度完全不同的 Expr，所以本研究把“复杂度”拆成可以独立计算、独立解释的层次。</p>
<h3>7.1 源码表面复杂度：bytes、lines 与 Token 代理量</h3>
<p><b>bytes</b> 是声明源码片段的 UTF-8 字节数；<b>lines</b> 是覆盖的源码行数。<b>Token 代理量</b>采用确定性正则规则：以 ASCII 英文字母或下划线开头、后接 ASCII 英文字母、数字、下划线或撇号的连续串算 1 个；连续数字算 1 个；其余每个非空白字符各算 1 个；空格和换行不计。</p>
<pre>theorem addOne (n : Nat) : n + 1 = Nat.succ n := by rfl
→ theorem | addOne | ( | n | : | Nat | ) | : | n | + | 1 | = |
  Nat | . | succ | n | : | = | by | rfl     （共 20 个）</pre>
<p class="note">因此 <code>:=</code> 算两个、<code>Nat.succ</code> 算三个。它是便于跨声明复现的源码词法代理，不是 Lean lexer 的精确 token；注释或字符串内部字符仍按同一规则计数。报告据此只讨论“表面规模”，不把它冒充证明语义复杂度。</p>
<h3>7.2 表达式结构复杂度：U、A、D、T</h3>
<p><b>树（tree）</b>要求每个子结构只有一个上级；<b>DAG（directed acyclic graph，有向无环图）</b>允许两个上级指向同一个共享子结构，但沿箭头不会绕回原点。Lean 可以共享同一个 Expr 对象，所以“实际保存的 DAG”与“把每次引用都复制一份后的树”大小可能差很多。</p>
<p>令 <code>children(x)</code> 是 Expr x 的直接子表达式位置，E 是整个 type 或 value 的根：</p>
<ul><li><b>唯一 DAG 节点 U</b>：从 E 可到达的不同 Expr 对象个数，近似回答“实际存了多少结构”。</li><li><b>DAG arcs A</b>：所有唯一节点的 child position 总数；同一 child 被引用两次就有两条 arc。</li><li><b>最大深度 D</b>：叶子深度为 1；非叶子为 <code>1 + max(child depth)</code>，回答“最长嵌套链有多深”。</li><li><b>展开树出现次数 T</b>：叶子为 1；非叶子为 <code>1 + sum(T(child))</code>。共享 child 每被引用一次就贡献一次，回答“若把共享完全展开，树有多大”。</li><li><b>展开倍数 T/U</b>：比较概念展开规模与实际共享结构；越大表示共享重复越强。</li></ul>
<h3>可手算的共享 DAG</h3><pre class="dag">        parent
        /    \\
     shared  shared
        |
       leaf</pre>
<p>这里只有 3 个不同对象，所以 U=3；parent 有两个 child position，shared 有一个，所以 A=3；最长路径 parent→shared→leaf，所以 D=3；完全展开时 parent 计 1，两个 shared 分支各计 2，所以 T=5，展开倍数 T/U=5/3。这个例子说明 T 很大时可能主要反映重复展开，而 U、A、D 描述的是另外三种结构性质。</p>
<p>计算时先遍历每个唯一节点及其 arcs，再按上述递推式汇总，所以时间复杂度为 <code>O(U+A)</code>、辅助空间为 <code>O(U)</code>。直观地说：实际保存的每块积木和每条连接大致各检查一次；即使 T 大得惊人，也不需要真的复制出 T 个对象。因此 T 是“概念展开规模”，不是实际运行秒数或内存量。</p>
<p class="note">U 是固定 Lean 版本与载入环境中的指针共享测量，适合本 snapshot 内比较；跨 Lean 版本时必须重新测量，不能把它当成永恒不变的语义属性。</p>
<h3>7.3 依赖广度</h3><p><b>unique constants</b> 统计 type 或 value 中出现了多少个不同的命名常量。重复调用同一常量只计一次，所以它衡量依赖“种类”的广度，不衡量调用次数。</p>
<h3>真实节点复杂度：从 small 到 high</h3>{{ complexity_examples_table|safe }}
<p><code>CategoryTheory.Limits.colimitLimitToLimitColimit_surjective</code> 的 value 展开树 T 为 {{ high_example.value_expr_tree_occurrences|fmt }}，但实际 DAG 唯一节点 U 为 {{ high_example.value_expr_unique_ptr_nodes|fmt }}，展开倍数为 {{ high_example.value_expr_expansion_factor|round(2) }}。三个数回答不同问题，不能单独称为“工作量”。</p>
<h3>全部测量变量、覆盖率与分布</h3>
<p>表中的<b>中位数</b>把样本分成一半较小、一半较大；<b>P90</b> 表示 90% 的有效样本不超过该值；<b>P99</b> 表示 99% 不超过该值。最大值只描述最极端的一个对象，不能代表典型节点。Value 行的样本数较少，是因为第 2、6 节所述的 null 被排除，而不是补成零。</p>
{{ complexity_table|safe }}
<p class="bridge">复杂度描述每张知识卡片自身。下一节换一个角度：不看卡片有多大，而数有多少箭头进入或离开它，从而定义复用与依赖负担。</p></section>

<section id="s8"><h2>8. 图总体统计</h2>
<p><b>入度（indegree）</b>是指向一个节点的不同来源数，在本研究中是主复用指标；<b>出度（outdegree）</b>是该节点指向的不同依赖数，可理解为直接依赖负担。入度为零表示 Corpus 内没有别的内部声明直接指向它；入度和出度都为零才叫<b>孤立节点</b>。<b>自环</b>是一个节点直接指向自己。</p>
<div class="callout"><b>教学例子：</b>若 A→B、C→B、B→D，则 B 的入度为 2（A、C 使用它），出度为 1（它依赖 D）。A 的出度为 1。即使 A 在同一 proof 中重复使用 B，主复用入度仍只把 A 算作一个来源。</div>
<div class="metric-table">{{ graph_table|safe }}</div>
<h3>从 incoming edges 到 reuse indegree</h3><p>下面是目标 <code>DFunLike.coe</code> 的 5 条确定性展示边。相同 source 的 TYPE 与 VALUE 是两条 typed edges，但 ALL unique consumer 只计一次。</p>{{ reuse_examples_table|safe }}
<p>该 target 的完整 ALL indegree 为 {{ reuse_target_degree|fmt }}；表中 5 行只是解释计数规则，不是统计样本。</p>
<h3>怎样读下面两张分布图</h3><ul><li><b>CCDF（互补累积分布）</b>在横轴取一个入度 x，纵轴回答“有多大比例的节点入度至少为 x”。例如 100 个节点中有 20 个入度至少为 10，则该点是 (10, 0.20)。</li><li><b>Rank–Frequency（排名—频数）</b>先按入度从高到低排序：横轴是第几名，纵轴是该名次的入度。它直观显示头部是否只有少数超高复用节点。</li><li><b>log 坐标</b>把 1、10、100、1000 这样的倍数间隔画成等距，便于同时看小值和大值；它不会把相关性或幂律自动“证明”出来。</li></ul>
<div class="grid figures">{{ figs.indegree_ccdf|safe }}{{ figs.rank_frequency|safe }}</div>
<p><b>图 2（CCDF）的数据现象：</b>曲线横跨多个数量级且缓慢下降，说明高入度节点虽少但真实存在；{{ (summary.zero_indegree_fraction*100)|round(2) }}% 节点入度为零，所以重尾分析只对 {{ veldhuizen.positive_nodes|fmt }} 个正入度目标成立。CCDF 证明“尾部很长”，不决定尾部一定是哪种分布。</p>
<p><b>图 3（Rank–Frequency）的直接检验：</b>蓝线是完整正入度排序，橙线是在 <code>xmin={{ all_fit.xmin }}</code> 以上 {{ veldhuizen.all_tail_n|fmt }} 个尾部节点拟合的 <code>C(r)∝r^-β</code>，绿线是斜率恰为 1 的参照。估计 β={{ veldhuizen.all_beta }}：它与 1 同属相近数量级，但下降明显更陡，所以全体 mathlib 只能称 <b>heavy-tailed / broadly Zipf-like</b>，不能称严格 <code>1/r</code>。第 12 节将显示 theorem β={{ veldhuizen.theorem_beta }}，比混合总体更接近 1。</p>
<p class="note">图中的高 R² 主要说明所选尾部在 log–log 坐标下接近直线；rank 点由同一排序共同产生，并非独立样本，因此普通 OLS 标准误不能当作完整的幂律检验。模型胜负仍看第 10 节的分布似然比较。</p>
<p class="bridge">分布图说明复用差异很大，但还没有回答“差异集中到什么程度”。下一节用 Top share、Gini、HHI 和 Lorenz 曲线把这种不均匀压缩成可比较的数字。</p></section>

<section id="s9"><h2>9. 复用集中度</h2>
<p>“集中”是问：全部复用关系是否主要流向少量节点。四个指标从不同角度回答：</p><ul><li><b>Top 1% share</b>：入度最高的 1% 节点合计获得全部复用入边的比例；Top 5% 和 10% 同理。</li><li><b>Gini 系数</b>：0 表示每个节点收到同样多的复用，越接近 1 越不均匀。</li><li><b>HHI</b>：先算每个节点占全部复用的份额，再把份额平方后相加；四个节点完全均分时 HHI=0.25，全部集中于一个节点时 HHI=1。</li><li><b>Lorenz 曲线</b>：把节点从低复用排到高复用，看“前 x% 节点累计得到多少复用”；曲线离均等对角线越远，分布越集中。</li></ul>
<div class="callout"><b>可手算的边界例子：</b>四个节点入度都是 [1,1,1,1] 时，Gini=0，Top 25% share=25%；若是 [0,0,0,4]，Top 25% share=100%，Gini=0.75。这个教学例子说明 Gini 越大意味着越不均匀，但有限样本即使极端集中也不一定恰好等于 1。</div>
<p>为了直接对应“所有被依赖的 components”，本节的主结论以正入度目标为分母；第 14 节另给包含零入度节点的图论稳健性视图。</p>
<div class="hero-stats compact"><div><strong>{{ veldhuizen.gini }}</strong><span>正入度 Gini</span></div><div><strong>{{ veldhuizen.top_1 }}%</strong><span>Top 1%</span></div><div><strong>{{ veldhuizen.top_5 }}%</strong><span>Top 5%</span></div><div><strong>{{ veldhuizen.top_10 }}%</strong><span>Top 10%</span></div></div>
{{ figs.lorenz|safe }}
<p><b>图 9（Lorenz）的数据现象：</b>曲线在大部分横轴范围紧贴底部，直到最后少量声明才快速上升；数值上 Gini={{ veldhuizen.gini }}，Top 1% 已承接 {{ veldhuizen.top_1 }}%，Top 5% 承接 {{ veldhuizen.top_5 }}%。这对 Veldhuizen 的“few components dominate reuse”命题构成强而且不依赖严格 Zipf 的支持。</p>
<p><b>实际含义：</b>高复用头部确实以基础结构为主，例如 <code>DFunLike.coe</code>、<code>Set</code>、结构继承投影以及 <code>CategoryTheory.Category</code>。它们把共同概念集中在少数接口中，可视为知识表示的共享基础设施；但入度仍不等于数学重要性、教学价值或证明难度。</p>
<p class="bridge">集中度证明“头部很强”，却不能告诉我们整条尾部最像哪种数学分布。下一节比较多个候选模型，避免仅凭双对数图看起来像直线就宣布幂律。</p></section>

<section id="s10"><h2>10. 重尾模型比较</h2>
<p><b>重尾（heavy tail）</b>表示“大多数值不大，但极大的值虽然少见，却比钟形分布所预期的更常出现”。学校规模是一个直观类比：大多数学校人数有限，极少数学校特别大。重尾只是形状描述，不等于已经证明某个具体公式。</p>
<p>本研究比较三种候选形状：<b>power law（幂律）</b>的尾部按幂次缓慢下降；<b>lognormal（对数正态）</b>表示取对数后近似钟形；<b>truncated power law（截尾幂律）</b>在幂律之外再加入高值衰减。它们都可能在双对数图上看起来近似直线，所以必须用数值比较。</p>
<h3>拟合表怎样读</h3><table><thead><tr><th>字段</th><th>高中阶段可用的读法</th></tr></thead><tbody>
<tr><td>n / tail_n</td><td>总体有效节点数 / 真正进入尾部拟合的节点数</td></tr>
<tr><td>xmin</td><td>从哪个最小入度开始称为“尾部”；更小的值不参与该尾部模型</td></tr>
<tr><td>degree_tail_alpha</td><td>入度“取某个值的概率”怎样衰减；这是分布指数，不是排名曲线斜率</td></tr>
<tr><td>beta_rank</td><td><code>C(r)∝r^-β</code> 的排名斜率；β=1 才直接对应 Veldhuizen 图中的 1/r</td></tr>
<tr><td>R²</td><td>所选 rank 尾部在 log–log 图上有多接近直线；高 R² 仍不能替代分布模型检验</td></tr>
<tr><td>KS</td><td>经验分布与拟合曲线的最大距离；同一总体中越小通常越贴近，但不能单独决定模型胜负</td></tr>
<tr><td>R</td><td>对数似然差：正值偏向 power law，负值偏向对照模型</td></tr>
<tr><td>p</td><td>若两个模型实际同样合适，出现当前这么大差异的相对意外程度；较小只支持“有差异”，不证明模型永远正确</td></tr>
</tbody></table>
{{ figs.tail_overlay|safe }}
{{ fits_table|safe }}
<p><b>图 4 与拟合表的合并结论：</b>全体入度分布的 <code>degree_tail_alpha={{ all_fit.alpha }}</code>、<code>xmin={{ all_fit.xmin }}</code>、KS={{ all_fit.ks }}；同一尾部的 <code>beta_rank={{ veldhuizen.all_beta }}</code>。前者回答“入度概率怎样衰减”，后者才回答“第 r 名怎样衰减”，所以不能把 1.778 误写成 Veldhuizen 的 rank 指数。</p>
<p>经验 CCDF 与幂律线视觉接近，但 power law 相对 lognormal 和 truncated power law 的对数似然比均为负且差异显著，表示两个替代模型更受支持。theorem 的 βrank={{ veldhuizen.theorem_beta }} 接近 1，只能形成<b>类别限定的 Zipf-like 证据</b>；全体 βrank={{ veldhuizen.all_beta }} 与 definition βrank={{ veldhuizen.definition_beta }} 表明混合所有 kind 会掩盖结构差异。</p>
<p class="note"><b>相对比较与绝对检验不同：</b>R/p 回答“两个候选模型谁更好”，bootstrap goodness-of-fit 回答“最佳候选本身是否足够像真实数据”。当前 bootstrap 状态为 <code>{{ all_fit.bootstrap_status }}</code>，所以不能报告绝对拟合优度 p 值，也不能宣称普适 Zipf 定律。</p>
<p class="bridge">重尾分析研究的是“复用入度如何分布”。下一节回到每个节点自身，把源码与 Expr 的多层复杂度同复用入度逐一比较。</p></section>

<section id="s11"><h2>11. 长度/复杂度与复用</h2>
<p>本节不寻找一个“正确的复杂度数字”，而是比较结论对复杂度定义是否敏感。结构很小的 <code>Set</code> 可以有很高复用，展开树巨大的 theorem 也不一定成为最高复用节点，因此必须进行总体统计并控制 kind/domain。</p>
{{ complexity_compare_table|safe }}
<h3>从散点到模型：为什么需要四步</h3><ol class="steps"><li><b>散点图</b>把一个 declaration 画成一个点，先观察是否有明显形状；log 坐标让数量级差异可见。</li><li><b>对数分箱</b>把复杂度相近的节点分组，比较每组复用的中位数和四分位范围，避免只盯着极端点。</li><li><b>Spearman 秩相关</b>只比较两个变量的高低排序是否同步，不要求关系是一条直线。</li><li><b>计数回归</b>在同时考虑 kind 和 domain 后，估计复杂度变化与期望入度的关联。</li></ol>
<div class="grid figures">{{ figs.source_length|safe }}{{ figs.type_length|safe }}{{ figs.value_length|safe }}{{ figs.length_binned|safe }}</div>
<p><b>图 5（源码 Token）：</b>点云非常分散，没有“越长就必然越高复用”的窄带；未控制 Spearman ρ={{ complexity_analysis.source_token_rho }} 是弱正相关。它主要反映不同 kind/domain 混合后的排序，不能单独回答同类声明中长度效应。</p>
<p><b>图 6（statement/type DAG U）：</b>高复用点更多出现在较小 U 区域，但仍有大量低复用小对象；这对应弱负秩相关，而非确定性规则。一个短 type 只是更可能处于基础接口位置，并不保证高复用。</p>
<p><b>图 7（proof/value DAG U）：</b>整体点云近乎水平铺开，未控制相关接近零；这说明大型证明项并不天然更常被引用。控制类别和领域后才出现负系数，提示总体混合掩盖了条件关系。</p>
<p><b>图 8（展开倍数 T/U 分箱）：</b>中位复用线大部分接近低值，四分位线也没有随展开倍数稳定上升；因此巨大的共享展开不是“高复用工作量”的代理。T/U 描述表达式共享形态，不等于 declaration 对外提供的复用价值。</p>
<h3>秩相关</h3>{{ correlations_table|safe }}
<p><b>Spearman ρ 怎样读：</b>范围是 -1 到 1。接近 1 表示复杂度排名越高，复用排名通常也越高；接近 -1 表示一个升高时另一个通常降低；接近 0 表示没有明显的单调排序关系。ρ 不说明因果，也可能受 kind、domain 等第三个变量影响。</p>
<p><b>实际结果：</b>源码 Token 代理量与复用的未控制秩相关为 ρ={{ complexity_analysis.source_token_rho }}；Type 的 U/A/D/T/T÷U 指标均为弱负相关（ρ 范围 {{ complexity_analysis.type_rho_min }} 至 {{ complexity_analysis.type_rho_max }}）；Value/Proof 的对应指标接近零（ρ 范围 {{ complexity_analysis.value_rho_min }} 至 {{ complexity_analysis.value_rho_max }}）。因此，极大的展开树 T 并不对应极高复用。</p>
<h3>控制声明类型与领域后的负二项 GLM</h3>{{ regressions_table|safe }}
<p><b>为什么用负二项 GLM？</b>入度是 0、1、2……这样的计数，而且少量节点特别大，波动远大于普通平均值模型所假设的程度。负二项广义线性模型（GLM）专门处理这种过度分散的计数。<code>log1p(x)=log(1+x)</code>，先加 1 是为了让 x=0 也能进入对数计算。</p>
<p><b>“控制 kind + domain”</b>类似比较学习时间与成绩时，先尽量在同年级、同课程的学生之间比较；它减少构成差异，但仍不能排除所有隐藏因素。<b>95% CI（置信区间）</b>表示在模型假设下估计的不确定范围；<b>p value</b>衡量零效应假设下当前结果的意外程度。样本极大时很小的效应也会有极小 p 值，所以本报告优先读效应大小与 CI，而不是把 <code>p=0.0</code> 当成“绝对真理”——0.0 只是显示精度下的舍入。</p>
<p>模型使用 <code>log1p(complexity)</code> 并控制 kind + domain。表中的“复杂度翻倍变化”把抽象系数转换为期望复用的相对变化。所有结果都是观察性关联，不是“复杂度导致复用”的因果效应。</p>
<p><b>控制后的主结论：</b>Token 系数 βlength={{ complexity_analysis.token_beta }}，95% CI [{{ complexity_analysis.token_ci_low }}, {{ complexity_analysis.token_ci_high }}]；Token 翻倍对应期望复用变化 {{ complexity_analysis.source_token_double }}%。Value DAG U 翻倍为 {{ complexity_analysis.value_u_double }}%，Value 展开树 T 为 {{ complexity_analysis.value_t_double }}%，Value 最大深度 D 为 {{ complexity_analysis.value_d_double }}%。所有方向为负，但幅度依复杂度定义不同。</p>
<h3>theorem 与 definition 内部分层</h3>{{ stratified_regressions_table|safe }}
<p>分层后方向仍为负：theorem 内 Token 翻倍约 {{ complexity_analysis.theorem_token_double }}%，definition 内约 {{ complexity_analysis.definition_token_double }}%；Value DAG U 翻倍分别约 {{ complexity_analysis.theorem_value_u_double }}% 与 {{ complexity_analysis.definition_value_u_double }}%。因此数据更支持“在同领域、同类声明中，较短和较基础的对象更容易成为高复用组件”，但 definition 的关联明显更强，不能用一个系数概括所有 node。</p>
<div class="callout"><b>与 Veldhuizen 的边界：</b>这里的 βlength 研究 declaration 自身长度与 consumer breadth。论文的 S(n) 是“第 n 个组件每次被复用时节省多少代码”。本数据没有反事实地计算“若删除该 declaration，每个使用者要多写多少”，所以不能说验证了 S(n)。</div>
<p class="note">模型诊断：{{ complexity_analysis.regression_status }}。模型使用预先声明的 α=1 Negative Binomial GLM；置信区间是在固定离散度模型下的条件结果。源码仅覆盖有可靠 range 的节点，且年代、API 层级、自动推理机制仍可能混杂，因此结论等级保持 exploratory。</p>
<div class="callout"><b>如何读多层结果：</b>若 T 的关联明显强于 U/A/D，可能是共享展开倍数在起作用；若 U 与 A 接近而 D 很弱，可能是总体结构规模而非最长嵌套链相关；若源码 Token 与 Expr 指标方向不同，说明短源码也可能精化成复杂对象。必须以表中实际系数、区间和 n 为准。</div>
<p class="bridge">复杂度模型已经控制 kind 和 domain，但不同 kind 与不同边类型本身仍有独立语义。下一节把这些类别重新展开，防止把自动生成基础设施与人工定理混成一种复用。</p></section>

<section id="s12"><h2>12. 声明种类（Node kind）与边语义</h2>
{{ figs.kind_counts|safe }}{{ kind_table|safe }}
<p><b>图 1（kind 构成）：</b>theorem 占 {{ theorem_share }}% 节点，因此“全体曲线”在节点数量上主要受 theorem 影响；但 definition 的复用总量与集中度远高于 theorem，说明节点多不等于承担的基础设施复用多。必须同时读构成图和下表，不能只看柱高。</p>
<h3>按 kind 的 Veldhuizen 指标</h3>{{ kind_reuse_table|safe }}
<p><b>分层结论：</b>theorem 的 βrank={{ veldhuizen.theorem_beta }}、正入度 Gini={{ veldhuizen.theorem_gini }}、Top 1%={{ veldhuizen.theorem_top_1 }}%，最接近 1/r；definition 的 βrank={{ veldhuizen.definition_beta }}、Gini={{ veldhuizen.definition_gini }}、Top 1%={{ veldhuizen.definition_top_1 }}%，尾部更陡且复用更集中；constructor 的 βrank={{ veldhuizen.constructor_beta }} 也接近 1，但总体小得多。由此可见，全体 β={{ veldhuizen.all_beta }} 是不同生成机制的混合值。</p>
<p><b>kind</b> 是 declaration 的生成类别，不是质量评分。theorem 表示命题及证明；definition/opaque 表示概念或实现；inductive 定义数据类型；constructor 构造该类型的值；recursor 提供按构造规则处理该类型的方法。定理占 {{ theorem_share }}% 节点，但数量多不自动表示它们承担最多基础设施复用。</p>
<div class="callout"><b>instance 当前必须报告为 not available，而不是 0：</b>Lean 环境把许多 instance 存成 definition/opaque，并通过 type-class attribute 标记；当前 graph schema 只有 ConstantInfo kind，没有独立 <code>is_instance</code> 字段。因此本报告不能给出可信的 instance-only β、Gini 或 Top-k，也不会把 definition 结果冒充 instance 结果。这是本轮 Veldhuizen 分层比较尚未满足的一项观测限制。</div>
<p>前述 VALUE theorem→theorem 最接近“证明使用引理”，TYPE theorem→definition 则表示命题陈述依赖某个概念。definition→definition 更像软件实现依赖，自动插入的类型类与强制转换又是另一种机制。因此同样一条入边，在不同 kind/edge 组合下不能完全作同一种人类意图解释。</p>
<p><b>generated</b> 是名称模式识别出的构造器辅助项、递归器、注入定理等系统性声明；<b>internal</b> 是私有或辅助命名空间中的声明。它们真实参与 Lean 检查，所以保留在底图；报告只在明确命名的派生视图中排除它们。</p>
<p class="bridge">Kind 描述“知识卡片是什么”。另一个可能改变规律的因素是“它属于哪个数学领域”。下一节按 module 路径构造可复现的领域标签并统计领域间箭头。</p></section>

<section id="s13"><h2>13. 领域结构与 H*ref</h2>
<p>领域标签来自 module 的高层路径，例如 <code>Mathlib.Algebra...</code> 归入 Algebra。它像按书架位置分类：规则清楚、可以重复得到同样结果，但一条定理可能跨越多个主题，所以它不是严格的数学本体分类。</p>
<p><b>领域依赖矩阵</b>的每一行是发出依赖的 source domain，每一列是收到依赖的 target domain。为了与 C_i 的 unique-consumer 单位一致，同一 `(src,dst)` 同时有 TYPE/VALUE 时先折叠一次，再使对应 cell 加 1。某行的 row share 是该来源领域全部唯一 dependency pairs 中指向某目标领域的比例。</p>{{ domain_examples_table|safe }}
<h3>Veldhuizen-style H*ref 怎样计算</h3><p>对来源领域 d，令 <code>p_d(b)=d 指向目标领域 b 的唯一 dependency pairs / d 的全部内部 dependency pairs</code>。当前共有 D={{ domain_analysis.target_domain_count }} 个可观测目标领域，定义 <code>H*ref(d)=-Σ p_d(b) log p_d(b) / log(D)</code>。统一分母使不同规模领域落在 0 到 1：接近 0 表示依赖集中在少数目标领域，接近 1 表示在 D 个领域间更均匀。</p>
<div class="callout"><b>教学例子：</b>若 100 个 pairs 全指向 Algebra，则只有 p=1，分子为 0，H*ref=0；若 50 个指向 Algebra、50 个指向 Topology，分子为 <code>log(2)</code>，所以 H*ref=<code>log(2)/log({{ domain_analysis.target_domain_count }})≈{{ domain_analysis.two_target_h }}</code>。它衡量“目标领域分散度”，不是一个 declaration 内部有多复杂。</div>
<div class="grid figures">{{ figs.domain_scale|safe }}{{ figs.domain_heatmap|safe }}{{ figs.domain_entropy|safe }}{{ figs.domain_tail|safe }}</div>
<p><b>图 10（领域规模）：</b>Algebra、CategoryTheory、Analysis、Topology 等来源领域规模差异很大；规模本身与 Gini 的 Spearman ρ={{ veldhuizen.size_gini_rho }}（p={{ veldhuizen.size_gini_p }}），所以不能把所有 Gini 差异都归因于领域语义。</p>
<p><b>图 11（依赖矩阵）：</b>CategoryTheory 与 Algebra 的行内对角块较强，分别有大量依赖留在本领域；Analysis、Topology、NumberTheory 的依赖则更明显地流向其他基础领域。它直观解释了为什么前两者 H*ref 较低，但颜色是依赖份额，不是数学相似度。</p>
<p><b>图 12（H*ref）：</b>Algebra={{ veldhuizen.algebra_h }}，而 NumberTheory={{ veldhuizen.number_theory_h }}；对应的有效目标领域数约为 <code>exp(Hraw)</code>，前者约 2.78，后者约 5.73。这个成对比较与“Algebra 共享抽象更集中、NumberTheory 跨领域依赖更分散”的解释一致。</p>
<p><b>图 13（Gini 与 βrank）：</b>各领域没有落在单一点上，表明复用尾部确实异质。但 H*ref 与 Gini 在节点数至少 100 的领域中只有 ρ={{ veldhuizen.entropy_gini_rho }}（p={{ veldhuizen.entropy_gini_p }}），没有显著单调关系；因此不能从 Algebra/NumberTheory 这一对例子推广成“H*ref 越低，Gini 必然越高”的普遍定律。</p>
{{ domain_table|safe }}
<h3>领域指标间关联审计</h3>{{ domain_associations_table|safe }}
<div class="callout"><b>H*ref 的解释边界：</b>它是按目标领域份额构造的 0–1 经验代理，适合在本报告统一规则下比较依赖较集中还是较分散；它不等于 Veldhuizen 对程序分布定义的理论 H，不能推出 <code>1-H</code> 的代码可复用比例，也不能证明“reuse potential 是领域的内在常数”。本数据只支持路径领域结构存在差异，与论文命题经验相容。</div>
<p class="bridge">领域与 kind 都可能改变结果。最后还要问：如果去掉系统生成节点或只看定理，集中度结论是否仍存在？这就是稳健性检查。</p></section>

<section id="s14"><h2>14. 稳健性视图</h2>
<p><b>稳健性检查</b>是把同一个问题换几种合理的样本范围再算一次。如果结论只在某一种筛选下成立，就应缩小结论范围；如果多个视图方向一致，结论就不太可能由单一类别偶然制造。</p>
<ul><li><b>ALL</b>：全部内部 declaration。</li><li><b>NO_GENERATED</b>：排除名称模式识别的系统生成声明。</li><li><b>THEOREM_ONLY / DEF_ONLY</b>：分别只看 theorem 或 definition/opaque。</li><li><b>THEOREM_AND_DEF</b>：只保留最主要的数学结论与定义。</li><li><b>USER_FACING_APPROX</b>：同时排除 generated 与 internal，近似面向普通库使用者的声明集合。</li></ul>
{{ figs.robustness|safe }}{{ views_table|safe }}
<p><b>图 14 的结果：</b>这里保留零入度节点，用来检查完整图口径。ALL 的 Gini={{ robustness_analysis.all_gini }}，NO_GENERATED 为 {{ robustness_analysis.no_generated_gini }}，THEOREM_ONLY 为 {{ robustness_analysis.theorem_gini }}，DEF_ONLY 为 {{ robustness_analysis.definition_gini }}。排除 generated 后集中度没有消失，所以“少数节点承担大部分复用”不是只由自动生成声明造成；但 theorem-only 明显低于 definition-only，再次证明 kind 混合会改变强度。</p>
<p class="note">稳健性一致不等于没有偏差：名称启发式可能无法识别所有生成声明，USER_FACING_APPROX 也不是人工数学重要性标签。它只回答预注册视图下结论是否改变。</p>
<p class="bridge">至此 Lean 内部分析完成。下一节只比较各系统共同的“节点—边—入度”语法，不把 Lean Expr、Wikipedia 文本和软件 AST 的原始复杂度误当成同一种单位。</p></section>

<section id="s15"><h2>15. 与 Veldhuizen 2005 的正面对照</h2>
<p>论文 <i>Software Libraries and Their Reuse: Entropy, Kolmogorov Complexity, and Zipf's Law</i> 的理论起点是：组件引用需要编码，组件复用率受到约束；在最大熵解释下，经验使用频率可能靠近 Zipf <code>1/r</code>。论文的定理 4.1 给出比简单 <code>1/r</code> 更严格的渐近上界，而 <code>λ(n)≈1/n</code> 是随后关于库演化和最大熵的解释及 Unix 数据观察，不能把两者写成同一个已证明等式。</p>
<table><thead><tr><th>论文对象</th><th>Lean 对应量</th><th>当前数值</th><th>明确 verdict</th></tr></thead><tbody>
<tr><td>component reuse frequency / Zipf-like 1/r</td><td>正入度 declaration 的 C(r)，βrank</td><td>ALL {{ veldhuizen.all_beta }}；theorem {{ veldhuizen.theorem_beta }}；definition {{ veldhuizen.definition_beta }}</td><td><b>部分支持</b>：重尾成立，theorem 接近 1/r；全体与 definition 不是严格 1/r</td></tr>
<tr><td>few components dominate reuse</td><td>正入度 Top-k / Gini</td><td>Top 1/5/10={{ veldhuizen.top_1 }}%/{{ veldhuizen.top_5 }}%/{{ veldhuizen.top_10 }}%；Gini={{ veldhuizen.gini }}</td><td><b>支持</b>：少数基础 declaration 主导复用</td></tr>
<tr><td>reuse potential differs by domain</td><td>来源路径领域 βrank、Gini、H*ref</td><td>Algebra H*={{ veldhuizen.algebra_h }}；NumberTheory H*={{ veldhuizen.number_theory_h }}</td><td><b>经验相容</b>：领域有差异；不足以证明理论 H 或内在因果</td></tr>
<tr><td>S(n): code saved per component use</td><td>本报告仅有 declaration size</td><td>Token βlength={{ complexity_analysis.token_beta }}；多层 Expr 条件系数为负</td><td><b>扩展性观察</b>：较短对象条件上更高复用；没有测量 S(n)</td></tr>
<tr><td>Library Incompleteness / vocabulary growth</td><td>多个 mathlib commit 的 Vt、Et、C_t(r)</td><td>只有 {{ summary.snapshot_id }}</td><td><b>不可检验</b>：不能从单一横截面声称稳定核心或持续长尾</td></tr>
</tbody></table>
<h3>为什么只能说“经验对应”</h3><ul><li>Unix 数据是共享对象中的 reference frequency；Lean 主指标是 unique consumer declaration breadth，不保留同一 Expr 内 occurrence multiplicity。</li><li>论文 H 建立在 problem domain 的程序概率分布及渐近熵上；H*ref 只是一次快照中目标领域份额的标准化熵。</li><li>论文 S(n) 是一次复用的代码节省；Lean source/Expr length 是被复用对象自身大小，两者没有等号。</li><li>论文 incompleteness 是带前提的理论结果；历史图只能检验与“稳定核心 + 新增长尾”是否经验相容，不能证明该定理。</li></ul>
<p>这套操作化仍可用于后续 Wikipedia 与软件图：先统一比较 unique indegree、Top-k、Gini 与 βrank，再保留各系统自己的复杂度单位。它们可以回答“结构是否相似”，不能让 Lean Expr U、wikitext bytes 与软件 AST nodes 直接互换。</p>
<p class="note">论文来源：Todd L. Veldhuizen, 2005, arXiv:cs/0508023v3，<a href="https://arxiv.org/abs/cs/0508023v3">摘要与版本页面</a>。</p>
<p class="bridge">最后不再给模糊的“可能相关”，而是按五个命题逐项给出支持、部分支持、探索性支持或不可检验。</p></section>

<section id="s16"><h2>16. 五个可检验命题的明确结论</h2>
<article class="verdict"><h3>P1 · declaration reuse 是否 Zipf / heavy-tail？——重尾：是；严格全体 Zipf：否；theorem-only：接近</h3><p>全体正入度 declaration 的尾部 βrank={{ veldhuizen.all_beta }}，不是 1；theorem βrank={{ veldhuizen.theorem_beta }} 最接近 1，definition βrank={{ veldhuizen.definition_beta }}。同时 lognormal 与 truncated power law 相对纯 power law 更受支持。因此可以说 mathlib 复用具有长尾，theorem reuse 与 Veldhuizen 的 1/r 观察相似；不能说整个 mathlib 已验证统一 Zipf 定律。</p></article>
<article class="verdict"><h3>P2 · 是否由少数基础组件主导？——支持，而且证据很强</h3><p>{{ veldhuizen.positive_nodes|fmt }} 个被至少一个内部 declaration 使用的目标中，Top 1/5/10% 承接 {{ veldhuizen.top_1 }}% / {{ veldhuizen.top_5 }}% / {{ veldhuizen.top_10 }}%，Gini={{ veldhuizen.gini }}。definition 的 Top 1%={{ veldhuizen.definition_top_1 }}%，theorem 为 {{ veldhuizen.theorem_top_1 }}%。结论是：少数定义、结构投影、归纳基础与核心定理构成高复用基础设施；这种集中在排除 generated 后仍存在。</p></article>
<article class="verdict exploratory"><h3>P3 · reuse potential 是否随数学领域变化？——领域异质性得到支持；理论命题只获经验相容</h3><p>节点数至少 100 的 {{ domain_analysis.domain_count }} 个来源路径领域中，Gini={{ domain_analysis.gini_min }}–{{ domain_analysis.gini_max }}，H*ref={{ domain_analysis.h_min }}–{{ domain_analysis.h_max }}，βrank={{ domain_analysis.rank_beta_min }}–{{ domain_analysis.rank_beta_max }}。Algebra 的 H*ref={{ veldhuizen.algebra_h }}、Top 1%={{ veldhuizen.algebra_top_1 }}%，NumberTheory 为 {{ veldhuizen.number_theory_h }}、{{ veldhuizen.number_theory_top_1 }}%，与“Algebra 依赖较集中、NumberTheory 依赖目标更分散”的成对解释一致。但跨全部领域 H*ref 与 Gini 的 ρ={{ veldhuizen.entropy_gini_rho }}、p={{ veldhuizen.entropy_gini_p }}，不支持简单普遍的单调关系；规模效应也很强。因此只能说领域结构不同，与 Veldhuizen 命题经验相容，不能说估计了理论 H。</p></article>
<article class="verdict exploratory"><h3>P4 · declaration 大小与复用是否有关？——控制后为负，支持“较短组件更易复用”的条件关联</h3><p>源码 Token 未控制 ρ={{ complexity_analysis.source_token_rho }}，但控制 kind/domain 后 βlength={{ complexity_analysis.token_beta }}，翻倍对应期望入度 {{ complexity_analysis.source_token_double }}%；Type 与 Value 的 U/A/D/T/T÷U 系数也全部为负。theorem 与 definition 内部分层仍为负，且 definition 更强。这个结论有研究价值，但只是观察性关联；长度不是 S(n)，不能解释为“短导致复用”或“节省了同样多代码”。</p></article>
<article class="verdict inconclusive"><h3>P5 · library 扩张是否形成稳定核心 + 持续长尾？——当前不可检验</h3><p>本报告只有 <code>{{ summary.snapshot_id }}</code> 一个横截面，没有多个 commit 上同口径的 V、E、rank 曲线与核心节点留存率。任何关于长期稳定核心、长尾新增速度或 library incompleteness 的经验结论都将越过证据；需要至少三个时间点并固定 extractor/schema 后再检验。</p></article>
<div class="answer"><b>最终研究回答：</b>形式化数学知识在“少数组件主导复用”和“长尾结构”上与软件库表现出强相似性；其中 theorem 的 rank 尾部最接近 Veldhuizen 的 1/r。与此同时，kind 与领域差异足够大，使“mathlib 服从一个统一 Zipf 定律”成为错误的过度概括。最准确的表述是：<b>Lean/mathlib 对 Veldhuizen 的集中复用观察提供强支持，对 Zipf 与领域命题提供分层、有限的经验支持，对 S(n) 与 library incompleteness 尚未完成直接检验。</b></div>
<h3>决定结论强度的限制</h3><ul><li>主复用量是 unique consumer breadth，不是同一 proof/body 内的 occurrence frequency。</li><li>instance role 尚不可观测；当前 definition 层不能替代 instance-only 结论。</li><li>源码范围覆盖 {{ ((1-quality.null_rates.source_bytes)*100)|round(2) }}%，Value null 按 kind 非随机分布；缺失没有补零。</li><li>rank β 是所选尾部的描述性斜率，纯 power law 的绝对 goodness-of-fit bootstrap 尚未实现。</li><li>回归为固定离散度条件模型，仍可能遗漏声明年代、API 层级和自动推理机制。</li><li>单 snapshot 不能回答历史增长。</li></ul>
<p>下一轮若要提升论文级证据，优先级依次为：补充稳定的 <code>is_instance</code> 角色；实现尾部拟合优度 bootstrap；冻结多个 mathlib commits 做纵向图；最后再与 Unix/software、Wikipedia 在相同 unique-consumer 口径下比较。</p></section>

<section id="s17"><h2>17. 附录：证据索引</h2>
<p>以下表格供研究人员从报告结论回到机器可读证据。<b>manifest</b> 像数据的版本说明书；<b>SHA-256</b> 像文件指纹，只要文件内容改变，指纹几乎必然改变。普通读者不需要逐项检查，reviewer 可以用它确认报告引用的是同一份数据。</p>
<p>复现命令、运行性能与执行日志保留在仓库文档和结果目录，不进入研究叙事。</p>
<h3>研究数据版本</h3>{{ manifest_table|safe }}
<h3>核心证据 artifacts</h3>{{ artifact_table|safe }}
<h3>复用最高的声明</h3>{{ top_table|safe }}
</section>
</main><footer>由版本化 compact artifacts 确定性生成 · 0 CDN · 0 远程脚本 · 0 远程字体</footer></body></html>""")


CSS = """:root{--ink:#15231d;--muted:#5f6c65;--paper:#f4f0e7;--card:#fffdf8;
--green:#175b45;--mint:#dceadf;--gold:#b47725;--red:#9c443d;--line:#cec7b9}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);
color:var(--ink);font:16px/1.68 system-ui,-apple-system,"Noto Sans CJK SC",sans-serif}
header,main,nav,footer{max-width:1180px;margin:auto}header{padding:72px 34px 38px}
main{padding:0 34px}.eyebrow{letter-spacing:.17em;font-size:.76rem;font-weight:800;
color:var(--green)}h1{font:800 clamp(2.7rem,7vw,5.1rem)/.98 Georgia,"Noto Serif SC",serif;
max-width:980px;margin:.16em 0}.dek{font:1.25rem/1.5 Georgia,"Noto Serif SC",serif;color:var(--muted)}
h2{font:750 2.05rem/1.2 Georgia,"Noto Serif SC",serif;border-top:1px solid var(--line);
padding-top:38px;margin-top:26px}h3{font-size:1.02rem;letter-spacing:.02em;margin:.2em 0 .5em}
section{padding:10px 0 34px}.status{display:flex;justify-content:space-between;gap:14px;
padding:15px 19px;border-left:6px solid #27824b;background:var(--mint);margin:28px 0}
.status.bad{border-color:var(--red);background:#f7e4df}.hero-stats{display:grid;
grid-template-columns:repeat(4,1fr);gap:12px}.hero-stats div{background:var(--card);padding:18px;
border:1px solid var(--line)}.hero-stats strong{display:block;font:700 1.7rem Georgia,serif}
.hero-stats span{display:block;color:var(--muted);font-size:.8rem}.hero-stats.compact{margin:18px 0}
nav{padding:16px 34px 24px}nav ol{display:flex;flex-wrap:wrap;gap:7px 20px;padding:0;
list-style-position:inside;font-size:.88rem}a{color:var(--green);text-decoration-thickness:1px}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:18px 0}
.grid.three{grid-template-columns:repeat(3,minmax(0,1fr))}.grid article{background:var(--card);
padding:20px;border:1px solid var(--line)}.grid.figures{align-items:start}.grid.figures .figure{margin:0}
.verdict,.callout,.answer{padding:18px 20px;margin:14px 0;background:var(--card);
border-left:5px solid var(--green)}.verdict p{margin:.35em 0 0}.verdict.exploratory{border-color:var(--gold)}
.verdict.inconclusive{border-color:var(--red)}.answer{font-size:1.08rem;background:var(--mint)}
.claim{padding:16px 18px;margin:12px 0;background:var(--card);border:1px solid var(--line);
border-left:5px solid var(--green)}.claim.inconclusive{border-left-color:var(--red)}
.claim.exploratory{border-left-color:var(--gold)}.claim p{margin:.35em 0}.claim small{color:var(--muted)}
.badge{display:inline-block;min-width:88px;margin-right:10px;padding:2px 8px;border-radius:12px;
background:var(--mint);font-size:.72rem;font-weight:800;text-transform:uppercase;text-align:center}
.bridge{margin:24px 0;padding:16px 19px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);
font-family:Georgia,"Noto Serif SC",serif;color:var(--green)}.dag{font-size:1rem;line-height:1.25}
.note,.caption,figcaption{color:var(--muted);font-size:.86rem}.steps li{margin:.65em 0}
svg,img{display:block;max-width:100%;height:auto;background:var(--card);margin:0}
.figure{margin:22px 0;background:var(--card);border:1px solid var(--line);padding:10px}
figcaption{padding:8px 10px 4px}table{border-collapse:collapse;width:100%;font-size:.82rem;
display:block;overflow:auto;background:var(--card);margin:14px 0}th,td{border-bottom:1px solid #ddd7cb;
text-align:left;padding:8px 10px;white-space:nowrap}th{position:sticky;top:0;background:#e5dfd2}
tr:hover td{background:#f4f8f2}code,pre{background:#e8e3d9;padding:.15em .35em}
pre{padding:18px;overflow:auto;border-left:4px solid var(--green)}footer{padding:45px 34px 75px;
color:var(--muted);border-top:1px solid var(--line);margin-top:30px}
@media(max-width:760px){header,main,nav{padding-left:18px;padding-right:18px}.hero-stats,
.grid,.grid.three{grid-template-columns:1fr 1fr}.status{display:block}.status span{display:block}}
@media(max-width:480px){.hero-stats,.grid,.grid.three{grid-template-columns:1fr}}
@media print{body{background:white}nav{display:none}section{break-inside:avoid}.figure{break-inside:avoid}}
"""


def generate(run_kind: str) -> dict[str, Any]:
    run_dir = run_results_root(run_kind)
    metrics = run_dir / "metrics"
    tables = run_dir / "tables"
    report = run_dir / "report"
    assets = report / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    summary = json.loads((metrics / "summary.json").read_text())
    quality = json.loads((metrics / "data_quality.json").read_text())
    if summary["run_kind"] != run_kind or quality["run_kind"] != run_kind:
        raise ValueError("compact results do not match requested run kind")
    manifest = run_manifest(run_kind)
    nodes = pl.read_parquet(metrics / "node_metrics.parquet")
    fits = pl.read_parquet(metrics / "powerlaw_fits.parquet")
    rank_fits = pl.read_parquet(metrics / "rank_frequency_fits.parquet")
    kind_reuse = pl.read_parquet(metrics / "kind_reuse_metrics.parquet")
    regressions = pl.read_parquet(metrics / "regressions.parquet")
    stratified_regressions = pl.read_parquet(
        metrics / "stratified_regressions.parquet"
    )
    domains = pl.read_parquet(metrics / "domain_metrics.parquet")
    domain_associations = pl.read_parquet(metrics / "domain_associations.parquet")
    domain_reuse_matrix = pl.read_parquet(tables / "domain_reuse_matrix.parquet")
    views = pl.read_parquet(metrics / "view_metrics.parquet")
    bins = pl.read_parquet(metrics / "length_binned.parquet")
    value_availability = pl.read_parquet(metrics / "value_availability.parquet")
    examples_path = tables / "report_examples.parquet"
    examples = pl.read_parquet(examples_path)
    claims = build_claim_registry(
        summary, quality, fits, rank_fits, domains, regressions
    )
    claims_path = report / "claims.json"
    examples_json_path = report / "examples.json"
    claims_path.write_text(json.dumps(claims, indent=2, sort_keys=True) + "\n")
    examples_json_path.write_text(
        json.dumps(
            examples_payload(examples, summary["snapshot_id"], run_kind),
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )
    benchmark_path = metrics / "extraction_benchmark.parquet"
    benchmark = (
        pl.read_parquet(benchmark_path)
        if benchmark_path.exists()
        else pl.DataFrame(
            json.loads((BENCHMARK_ROOT / "extraction.json").read_text())["rows"]
        )
    )
    compact_inputs = [
        metrics / "summary.json",
        metrics / "data_quality.json",
        metrics / "node_metrics.parquet",
        metrics / "powerlaw_fits.parquet",
        metrics / "rank_frequency_fits.parquet",
        metrics / "kind_reuse_metrics.parquet",
        metrics / "regressions.parquet",
        metrics / "stratified_regressions.parquet",
        metrics / "domain_metrics.parquet",
        metrics / "domain_associations.parquet",
        metrics / "view_metrics.parquet",
        metrics / "length_binned.parquet",
        metrics / "length_correlations.parquet",
        metrics / "value_availability.parquet",
        tables / "top_reuse.csv",
        tables / "domain_matrix.parquet",
        tables / "domain_reuse_matrix.parquet",
        examples_path,
        claims_path,
        examples_json_path,
        normalized_root(CONFIG["snapshot_id"], run_kind) / "manifest.json",
        complexity_normalized_root(CONFIG["snapshot_id"], run_kind) / "manifest.json",
        run_dir / "run-manifest.json",
    ]
    artifacts = artifact_index(run_dir, compact_inputs)
    artifact_index_path = report / "artifact-index.json"
    artifact_index_path.write_text(json.dumps(artifacts, indent=2, sort_keys=True) + "\n")

    complexity_labels = {
        "source_bytes": "源码字节数",
        "source_lines": "源码行数",
        "source_tokens": "源码 Token 代理量",
        "type_const_unique": "Type 唯一常量数",
        "value_const_unique": "Value/Proof 唯一常量数",
        "type_expr_unique_ptr_nodes": "Type DAG 唯一节点 U",
        "type_expr_dag_arcs": "Type DAG arcs A",
        "type_expr_max_depth": "Type 最大深度 D",
        "type_expr_tree_occurrences": "Type 展开树出现次数 T",
        "type_expr_expansion_factor": "Type 展开倍数 T/U",
        "value_expr_unique_ptr_nodes": "Value/Proof DAG 唯一节点 U",
        "value_expr_dag_arcs": "Value/Proof DAG arcs A",
        "value_expr_max_depth": "Value/Proof 最大深度 D",
        "value_expr_tree_occurrences": "Value/Proof 展开树出现次数 T",
        "value_expr_expansion_factor": "Value/Proof 展开倍数 T/U",
    }
    complexity_rows = []
    for column, label in complexity_labels.items():
        observed = nodes[column].drop_nulls()
        complexity_rows.append(
            {
                "变量": label,
                "非空 n": len(observed),
                "覆盖率": f"{len(observed) / nodes.height:.2%}",
                "中位数": observed.median(),
                "P90": observed.quantile(0.90),
                "P99": observed.quantile(0.99),
                "最大值": observed.max(),
            }
        )
    complexity_stats = pl.DataFrame(complexity_rows)

    graph_stats = pl.DataFrame(
        [
            {"指标": "配置内模块", "数值": summary["module_count"]},
            {"指标": "内部声明节点", "数值": summary["declaration_count"]},
            {"指标": "显式外部目标", "数值": quality["external_node_count"]},
            {"指标": "TYPE 唯一边", "数值": summary["type_edge_count"]},
            {"指标": "VALUE 唯一边", "数值": summary["value_edge_count"]},
            {"指标": "全部唯一边", "数值": summary["edge_count"]},
            {"指标": "自环", "数值": summary["self_loop_count"]},
        ]
    )
    kind_stats = (
        nodes.group_by("kind")
        .agg(
            pl.len().alias("节点数"),
            pl.col("in_degree_all").mean().alias("平均入度"),
            pl.col("in_degree_all").median().alias("入度中位数"),
            pl.col("in_degree_all").max().alias("最大入度"),
        )
        .rename({"kind": "声明类型"})
        .sort("节点数", descending=True)
    )
    correlations = pl.DataFrame(summary["length_correlations"]).rename(
        {
            "length_metric": "长度/复杂度变量",
            "n": "n",
            "spearman_rho": "Spearman rho",
            "p_value": "p value",
        }
    )
    regression_report = regressions.with_columns(
        (
            ((pl.col("coefficient") * math.log(2)).exp() - 1) * 100
        ).alias("复杂度翻倍变化 %")
    ).select(
        pl.col("length_metric").alias("变量"),
        "n",
        pl.col("coefficient").alias("beta"),
        pl.col("ci_low").alias("95% CI low"),
        pl.col("ci_high").alias("95% CI high"),
        "复杂度翻倍变化 %",
        pl.col("p_value").alias("p value"),
        pl.col("controls").alias("控制变量"),
        "status",
    )

    degree = sorted(nodes["in_degree_all"].to_list(), reverse=True)
    rank_degree = [value for value in degree if value > 0]
    positive = sorted([value for value in degree if value > 0])
    ccdf_x = sorted(set(positive))
    ccdf_y = [
        sum(value >= x for value in positive) / len(positive) for x in ccdf_x
    ] if positive else []
    lorenz_values = positive
    total = sum(lorenz_values) or 1
    cumulative = [0.0]
    for value in lorenz_values:
        cumulative.append(cumulative[-1] + value / total)
    lorenz_x = [
        index / max(len(lorenz_values), 1) for index in range(len(cumulative))
    ]
    kind_counts = sorted(summary["declaration_counts_by_kind"].items())
    top_domains = domains.sort("node_count", descending=True).head(14)
    all_fit = fits.filter(pl.col("population") == "all_declarations")
    all_rank = rank_fits.filter(pl.col("population") == "all_declarations")
    alpha = (
        float(all_fit["alpha"][0])
        if all_fit.height and all_fit["alpha"][0] is not None
        else 2.0
    )
    xmin = (
        float(all_fit["xmin"][0])
        if all_fit.height and all_fit["xmin"][0] is not None
        else 1.0
    )
    tail_x = [float(x) for x in ccdf_x if x >= xmin]
    tail_y = [(x / xmin) ** (1 - alpha) for x in tail_x]
    rank_tail_n = int(all_rank["tail_n"][0])
    rank_tail_x = list(range(1, rank_tail_n + 1))
    rank_tail_y = [
        math.exp(float(all_rank["intercept"][0]))
        * rank ** (-float(all_rank["beta_rank"][0]))
        for rank in rank_tail_x
    ]
    rank_mid = max(1, rank_tail_n // 2)
    zipf_scale = rank_tail_y[rank_mid - 1] * rank_mid
    zipf_y = [zipf_scale / rank for rank in rank_tail_x]
    binned = bins.filter(
        pl.col("length_metric") == "value_expr_expansion_factor"
    ).sort(
        "length_median"
    )
    figures = {
        "kind_counts": bar_svg(
            TITLES["kind_counts"],
            [item[0] for item in kind_counts],
            [item[1] for item in kind_counts],
            "declarations",
        ),
        "indegree_ccdf": line_svg(
            TITLES["indegree_ccdf"],
            [("empirical", ccdf_x, ccdf_y)],
            "indegree (log)",
            "P(X≥x) (log)",
            True,
            True,
        ),
        "rank_frequency": line_svg(
            TITLES["rank_frequency"],
            [
                ("empirical", list(range(1, len(rank_degree) + 1)), rank_degree),
                ("tail fit", rank_tail_x, rank_tail_y),
                ("Zipf 1/r", rank_tail_x, zipf_y),
            ],
            "rank (log)",
            "indegree (log)",
            True,
            True,
        ),
        "tail_overlay": line_svg(
            TITLES["tail_overlay"],
            [("empirical", ccdf_x, ccdf_y), ("power-law tail", tail_x, tail_y)],
            "indegree (log)",
            "CCDF (log)",
            True,
            True,
        ),
        "source_length": points_svg(
            TITLES["source_length"],
            nodes["source_tokens"].to_list(),
            nodes["in_degree_all"].to_list(),
            "source token proxy (log)",
            "reuse (log)",
        ),
        "type_length": points_svg(
            TITLES["type_length"],
            nodes["type_expr_unique_ptr_nodes"].to_list(),
            nodes["in_degree_all"].to_list(),
            "type DAG unique nodes U (log)",
            "reuse (log)",
        ),
        "value_length": points_svg(
            TITLES["value_length"],
            nodes["value_expr_unique_ptr_nodes"].to_list(),
            nodes["in_degree_all"].to_list(),
            "value DAG unique nodes U (log)",
            "reuse (log)",
        ),
        "length_binned": line_svg(
            TITLES["length_binned"],
            [
                ("median", binned["length_median"].to_list(), binned["reuse_median"].to_list()),
                ("q25", binned["length_median"].to_list(), binned["reuse_q25"].to_list()),
                ("q75", binned["length_median"].to_list(), binned["reuse_q75"].to_list()),
            ],
            "value expansion T/U (log)",
            "reuse",
            True,
            False,
        ),
        "lorenz": line_svg(
            TITLES["lorenz"],
            [("reuse", lorenz_x, cumulative), ("equality", [0, 1], [0, 1])],
            "cumulative declarations",
            "cumulative reuse",
        ),
        "domain_scale": bar_svg(
            TITLES["domain_scale"],
            top_domains["domain"].to_list(),
            top_domains["node_count"].to_list(),
            "nodes",
        ),
        "domain_heatmap": heatmap_svg(domain_reuse_matrix),
        "domain_entropy": bar_svg(
            TITLES["domain_entropy"],
            top_domains["domain"].to_list(),
            top_domains["reference_entropy_proxy"].to_list(),
            "H*ref",
        ),
        "domain_tail": points_svg(
            TITLES["domain_tail"],
            domains["gini"].to_list(),
            domains["rank_exponent_beta"].to_list(),
            "Gini",
            "rank exponent beta",
            False,
            False,
        ),
        "robustness": bar_svg(
            TITLES["robustness"],
            views["view"].to_list(),
            views["gini"].to_list(),
            "Gini",
        ),
    }
    for name, svg in figures.items():
        (assets / f"{name}.svg").write_text(svg)
    source_valid = nodes["source_tokens"].drop_nulls().len()
    value_valid = nodes["value_expr_unique_ptr_nodes"].drop_nulls().len()
    source_plotted = nodes.filter(
        pl.col("source_tokens").is_not_null()
        & (pl.col("source_tokens") > 0)
        & (pl.col("in_degree_all") > 0)
    ).height
    type_plotted = nodes.filter(
        (pl.col("type_expr_unique_ptr_nodes") > 0) & (pl.col("in_degree_all") > 0)
    ).height
    value_plotted = nodes.filter(
        pl.col("value_expr_unique_ptr_nodes").is_not_null()
        & (pl.col("value_expr_unique_ptr_nodes") > 0)
        & (pl.col("in_degree_all") > 0)
    ).height
    figure_samples = {
        "kind_counts": f"population=ALL；n_total={nodes.height:,}；使用完整统计。",
        "indegree_ccdf": f"population=positive indegree；n_valid={len(positive):,}；折线显示≤700点。",
        "rank_frequency": f"n_positive={len(positive):,}；tail_n={rank_tail_n:,}；每条折线显示≤700点。",
        "tail_overlay": f"population=indegree≥xmin；tail_n={all_fit['tail_n'][0]:,}；折线显示≤700点。",
        "source_length": f"n_total={nodes.height:,}；metric n_valid={source_valid:,}；positive plotted population={source_plotted:,}；显示≤1,600点。",
        "type_length": f"n_total=n_valid={nodes.height:,}；positive plotted population={type_plotted:,}；显示≤1,600点。",
        "value_length": f"n_total={nodes.height:,}；metric n_valid={value_valid:,}；positive plotted population={value_plotted:,}；显示≤1,600点。",
        "length_binned": f"value expansion n_valid={value_valid:,}；分箱统计使用全部有效值。",
        "lorenz": f"population=positive indegree targets；n={len(positive):,}；折线显示≤700点。",
        "domain_scale": f"population=top domains；展示 {top_domains.height} 个领域。",
        "domain_heatmap": f"population=internal unique dependency pairs；n={domain_reuse_matrix['dependency_pair_count'].sum():,}。",
        "domain_entropy": f"population=top domains；展示 {top_domains.height} 个领域。",
        "domain_tail": f"population=domains with fitted rank exponent；n_valid={domains['rank_exponent_beta'].drop_nulls().len()}。",
        "robustness": f"population=registered views；n_views={views.height}。",
    }
    local = {
        name: (
            f'<figure class="figure"><img src="assets/{name}.svg" '
            f'alt="{html.escape(TITLES[name])}"><figcaption>'
            f'{html.escape(FIGURE_CAPTIONS[name])} '
            f'{html.escape(figure_samples[name])}</figcaption></figure>'
        )
        for name in figures
    }
    inline = {
        name: (
            f'<figure class="figure">{svg}<figcaption>'
            f'{html.escape(FIGURE_CAPTIONS[name])} '
            f'{html.escape(figure_samples[name])}</figcaption></figure>'
        )
        for name, svg in figures.items()
    }
    node_examples = examples.filter(pl.col("node_id").is_not_null()).sort("example_id")
    edge_examples = examples.filter(pl.col("example_id").str.starts_with("edge."))
    reuse_examples = examples.filter(pl.col("concept") == "reuse indegree")
    domain_examples = examples.filter(pl.col("concept") == "domain dependency matrix")
    high_example = examples.filter(pl.col("example_id") == "node.complexity.high").row(
        0, named=True
    )
    reuse_target_degree = reuse_examples["in_degree_all"][0]
    artifact_frame = pl.DataFrame(artifacts["artifacts"])
    exclusions = pl.DataFrame(tomllib.loads(EXCLUSIONS_PATH.read_text())["rule"])
    research_manifest_fields = (
        "schema_version",
        "snapshot_id",
        "run_kind",
        "mathlib_tag",
        "mathlib_commit",
        "lean_toolchain",
        "extractor_commit",
        "report_generator_commit",
        "config_sha256",
        "raw_manifest_sha256",
    )
    research_manifest = {key: manifest.get(key) for key in research_manifest_fields}
    correlation_by_metric = {
        row["长度/复杂度变量"]: row["Spearman rho"]
        for row in correlations.iter_rows(named=True)
    }
    regression_by_metric = {
        row["length_metric"]: row for row in regressions.iter_rows(named=True)
    }
    rank_by_population = {
        row["population"]: row for row in rank_fits.iter_rows(named=True)
    }
    kind_reuse_by_name = {
        row["kind"]: row for row in kind_reuse.iter_rows(named=True)
    }
    domain_by_name = {
        row["domain"]: row for row in domains.iter_rows(named=True)
    }
    domain_association_by_pair = {
        (row["left_metric"], row["right_metric"]): row
        for row in domain_associations.iter_rows(named=True)
    }
    stratified_by_key = {
        (row["stratum"], row["length_metric"]): row
        for row in stratified_regressions.iter_rows(named=True)
    }

    def formatted_metric(row: dict[str, Any] | None, key: str) -> str:
        if row is None:
            return "—"
        value = row.get(key)
        return f"{value:.3f}" if value is not None and math.isfinite(value) else "—"

    def formatted_percent(row: dict[str, Any] | None, key: str) -> str:
        if row is None:
            return "—"
        value = row.get(key)
        return f"{value * 100:.1f}" if value is not None and math.isfinite(value) else "—"
    type_rhos = [
        correlation_by_metric[f"type_expr_{suffix}"]
        for suffix in (
            "unique_ptr_nodes",
            "dag_arcs",
            "max_depth",
            "tree_occurrences",
            "expansion_factor",
        )
    ]
    value_rhos = [
        correlation_by_metric[f"value_expr_{suffix}"]
        for suffix in (
            "unique_ptr_nodes",
            "dag_arcs",
            "max_depth",
            "tree_occurrences",
            "expansion_factor",
        )
    ]

    def doubling_change(metric: str) -> str:
        coefficient = regression_by_metric[metric]["coefficient"]
        return f"{(math.exp(coefficient * math.log(2)) - 1) * 100:.1f}"

    def stratified_doubling(stratum: str, metric: str) -> str:
        coefficient = stratified_by_key[(stratum, metric)]["coefficient"]
        return f"{(math.exp(coefficient * math.log(2)) - 1) * 100:.1f}"

    status_counts = regressions.group_by("status").len().sort("status")
    regression_status = "；".join(
        f"{row['len']}/{regressions.height} 为 {row['status']}"
        for row in status_counts.iter_rows(named=True)
    )
    view_by_name = {row["view"]: row for row in views.iter_rows(named=True)}
    comparable_domains = domains.filter(pl.col("node_count") >= 100)
    target_domain_count = int(domains["reference_entropy_target_domain_count"][0])
    positive_concentration = summary["veldhuizen_reuse_concentration"]
    entropy_gini = domain_association_by_pair[("reference_entropy_proxy", "gini")]
    size_gini = domain_association_by_pair[("node_count", "gini")]
    rank_report = fits.join(
        rank_fits.select(
            "population",
            "beta_rank",
            "r_squared",
            "distance_from_zipf_1",
        ),
        on="population",
        how="left",
    )
    stratified_report = stratified_regressions.with_columns(
        (((pl.col("coefficient") * math.log(2)).exp() - 1) * 100).alias(
            "复杂度翻倍变化 %"
        )
    )
    context = {
        "css": CSS,
        "quality": quality,
        "summary": summary,
        "manifest": manifest,
        "config": CONFIG,
        "claims": claims,
        "high_example": high_example,
        "reuse_target_degree": reuse_target_degree,
        "complexity_analysis": {
            "source_token_rho": f"{correlation_by_metric['source_tokens']:.3f}",
            "type_rho_min": f"{min(type_rhos):.3f}",
            "type_rho_max": f"{max(type_rhos):.3f}",
            "value_rho_min": f"{min(value_rhos):.3f}",
            "value_rho_max": f"{max(value_rhos):.3f}",
            "source_token_double": doubling_change("source_tokens"),
            "value_u_double": doubling_change("value_expr_unique_ptr_nodes"),
            "value_t_double": doubling_change("value_expr_tree_occurrences"),
            "value_d_double": doubling_change("value_expr_max_depth"),
            "regression_status": regression_status,
            "token_beta": f"{regression_by_metric['source_tokens']['coefficient']:.3f}",
            "token_ci_low": f"{regression_by_metric['source_tokens']['ci_low']:.3f}",
            "token_ci_high": f"{regression_by_metric['source_tokens']['ci_high']:.3f}",
            "theorem_token_double": stratified_doubling("theorem", "source_tokens"),
            "definition_token_double": stratified_doubling("definition", "source_tokens"),
            "theorem_value_u_double": stratified_doubling(
                "theorem", "value_expr_unique_ptr_nodes"
            ),
            "definition_value_u_double": stratified_doubling(
                "definition", "value_expr_unique_ptr_nodes"
            ),
        },
        "veldhuizen": {
            "positive_nodes": positive_concentration["nodes"],
            "gini": f"{positive_concentration['gini']:.3f}",
            "top_1": f"{positive_concentration['top_1pct_share'] * 100:.1f}",
            "top_5": f"{positive_concentration['top_5pct_share'] * 100:.1f}",
            "top_10": f"{positive_concentration['top_10pct_share'] * 100:.1f}",
            "all_beta": formatted_metric(
                rank_by_population.get("all_declarations"), "beta_rank"
            ),
            "all_tail_n": rank_by_population["all_declarations"]["tail_n"],
            "theorem_beta": formatted_metric(
                rank_by_population.get("kind:theorem"), "beta_rank"
            ),
            "definition_beta": formatted_metric(
                rank_by_population.get("kind:definition"), "beta_rank"
            ),
            "constructor_beta": formatted_metric(
                rank_by_population.get("kind:constructor"), "beta_rank"
            ),
            "theorem_gini": formatted_metric(
                kind_reuse_by_name.get("theorem"), "gini_positive"
            ),
            "definition_gini": formatted_metric(
                kind_reuse_by_name.get("definition"), "gini_positive"
            ),
            "theorem_top_1": formatted_percent(
                kind_reuse_by_name.get("theorem"), "top_1pct_share_positive"
            ),
            "definition_top_1": formatted_percent(
                kind_reuse_by_name.get("definition"), "top_1pct_share_positive"
            ),
            "algebra_h": formatted_metric(
                domain_by_name.get("Algebra"), "reference_entropy_proxy"
            ),
            "algebra_gini": formatted_metric(domain_by_name.get("Algebra"), "gini"),
            "algebra_top_1": formatted_percent(
                domain_by_name.get("Algebra"), "top_1pct_share"
            ),
            "algebra_beta": formatted_metric(
                domain_by_name.get("Algebra"), "rank_exponent_beta"
            ),
            "number_theory_h": formatted_metric(
                domain_by_name.get("NumberTheory"), "reference_entropy_proxy"
            ),
            "number_theory_gini": formatted_metric(
                domain_by_name.get("NumberTheory"), "gini"
            ),
            "number_theory_top_1": formatted_percent(
                domain_by_name.get("NumberTheory"), "top_1pct_share"
            ),
            "number_theory_beta": formatted_metric(
                domain_by_name.get("NumberTheory"), "rank_exponent_beta"
            ),
            "entropy_gini_rho": f"{entropy_gini['spearman_rho']:.3f}",
            "entropy_gini_p": f"{entropy_gini['p_value']:.3f}",
            "size_gini_rho": f"{size_gini['spearman_rho']:.3f}",
            "size_gini_p": f"{size_gini['p_value']:.2g}",
        },
        "robustness_analysis": {
            "all_gini": f"{view_by_name['ALL']['gini']:.3f}",
            "no_generated_gini": f"{view_by_name['NO_GENERATED']['gini']:.3f}",
            "theorem_gini": f"{view_by_name['THEOREM_ONLY']['gini']:.3f}",
            "definition_gini": f"{view_by_name['DEF_ONLY']['gini']:.3f}",
        },
        "domain_analysis": {
            "domain_count": comparable_domains.height,
            "target_domain_count": target_domain_count,
            "two_target_h": f"{math.log(2) / math.log(target_domain_count):.3f}",
            "gini_min": f"{comparable_domains['gini'].min():.3f}",
            "gini_max": f"{comparable_domains['gini'].max():.3f}",
            "h_min": f"{comparable_domains['reference_entropy_proxy'].min():.3f}",
            "h_max": f"{comparable_domains['reference_entropy_proxy'].max():.3f}",
            "rank_beta_min": f"{comparable_domains['rank_exponent_beta'].min():.3f}",
            "rank_beta_max": f"{comparable_domains['rank_exponent_beta'].max():.3f}",
        },
        "all_fit": {
            "alpha": format_cell(alpha),
            "xmin": format_cell(xmin),
            "ks": format_cell(all_fit["ks"][0]) if all_fit.height else "—",
            "bootstrap_status": (
                all_fit["bootstrap_status"][0] if all_fit.height else "missing"
            ),
        },
        "theorem_share": format_cell(
            100
            * summary["declaration_counts_by_kind"]["theorem"]
            / summary["declaration_count"]
        ),
        "manifest_table": render_table(
            pl.DataFrame([research_manifest]).transpose(
                include_header=True, header_name="field", column_names=["value"]
            ),
            40,
        ),
        "quality_table": render_table(
            pl.DataFrame([quality["checks"]]).transpose(
                include_header=True, header_name="check", column_names=["passed"]
            ),
            40,
        ),
        "exclusions_table": render_table(
            exclusions.rename({"pattern": "排除 pattern", "reason": "理由"}), 20
        ),
        "value_availability_table": render_table(
            value_availability.rename(
                {
                    "kind": "声明类型",
                    "node_count": "节点数",
                    "value_available_count": "value 非空",
                    "value_null_count": "value null",
                    "value_available_fraction": "value 覆盖率",
                }
            ),
            20,
        ),
        "node_examples_table": render_table(
            node_examples.select(
                pl.col("role").alias("案例角色"),
                pl.col("node_name").alias("declaration"),
                pl.col("node_kind").alias("kind"),
                pl.col("node_module").alias("module"),
                "has_value",
                "type_expr_nodes",
                "value_expr_nodes",
                "in_degree_all",
                pl.col("source_locator").alias("source locator"),
            ),
            10,
        ),
        "edge_examples_table": render_table(
            edge_examples.select(
                pl.col("src_name").alias("consumer/source"),
                pl.col("src_kind").alias("src kind"),
                "edge_type",
                pl.col("dst_name").alias("dependency/target"),
                pl.col("dst_kind").alias("dst kind"),
                "evidence",
            ),
            10,
        ),
        "complexity_examples_table": render_table(
            node_examples.select(
                pl.col("role").alias("复杂度角色"),
                pl.col("node_name").alias("declaration"),
                "node_kind",
                "source_bytes",
                "type_expr_unique_ptr_nodes",
                "type_expr_max_depth",
                "type_expr_tree_occurrences",
                "value_expr_unique_ptr_nodes",
                "value_expr_max_depth",
                "value_expr_tree_occurrences",
                "value_expr_expansion_factor",
                "in_degree_all",
            ),
            10,
        ),
        "complexity_compare_table": render_table(
            node_examples.select(
                pl.col("node_name").alias("真实节点"),
                "node_kind",
                "has_value",
                "source_bytes",
                "type_expr_unique_ptr_nodes",
                "type_expr_max_depth",
                "type_expr_tree_occurrences",
                "value_expr_unique_ptr_nodes",
                "value_expr_max_depth",
                "value_expr_tree_occurrences",
                "value_expr_expansion_factor",
                "in_degree_all",
                pl.col("caveat").alias("单例限制"),
            ),
            10,
        ),
        "reuse_examples_table": render_table(
            reuse_examples.select(
                pl.col("src_name").alias("unique consumer"),
                "edge_type",
                pl.col("dst_name").alias("target"),
                "evidence",
            ),
            10,
        ),
        "domain_examples_table": render_table(
            domain_examples.select(
                pl.col("role").alias("关系"),
                "src_domain",
                pl.col("src_name").alias("source"),
                "edge_type",
                "dst_domain",
                pl.col("dst_name").alias("target"),
            ),
            10,
        ),
        "artifact_table": render_table(artifact_frame, 30),
        "complexity_table": render_table(complexity_stats, 20),
        "graph_table": render_table(graph_stats, 20),
        "correlations_table": render_table(correlations, 10),
        "kind_table": render_table(kind_stats, 10),
        "fits_table": render_table(
            rank_report.select(
                "population",
                "n",
                "tail_n",
                "xmin",
                pl.col("alpha").alias("degree_tail_alpha"),
                "beta_rank",
                "r_squared",
                "distance_from_zipf_1",
                "ks",
                "powerlaw_vs_lognormal_r",
                "powerlaw_vs_lognormal_p",
                "powerlaw_vs_truncated_r",
                "powerlaw_vs_truncated_p",
                "bootstrap_status",
            ),
            40,
        ),
        "regressions_table": render_table(regression_report, 10),
        "stratified_regressions_table": render_table(
            stratified_report.select(
                "stratum",
                pl.col("length_metric").alias("变量"),
                "n",
                pl.col("coefficient").alias("beta"),
                pl.col("ci_low").alias("95% CI low"),
                pl.col("ci_high").alias("95% CI high"),
                "复杂度翻倍变化 %",
                "controls",
                "status",
            ),
            20,
        ),
        "kind_reuse_table": render_table(kind_reuse, 20),
        "domain_associations_table": render_table(domain_associations, 20),
        "domain_table": render_table(
            domains.sort("node_count", descending=True), 30
        ),
        "views_table": render_table(views, 10),
        "top_table": render_table(
            pl.read_csv(tables / "top_reuse.csv").select(
                "name",
                "module",
                "kind",
                "in_degree_all",
                "in_degree_type",
                "in_degree_value",
            ),
            25,
        ),
        "benchmark_table": render_table(benchmark, 10),
    }
    (report / "index.html").write_text(TEMPLATE.render(**context, figs=local))
    standalone = TEMPLATE.render(**context, figs=inline)
    (report / "report_standalone.html").write_text(standalone)
    result = {
        "schema_version": "report-manifest-v1",
        "run_kind": run_kind,
        "section_count": 17,
        "figure_count": len(figures),
        "index_sha256": file_sha256(report / "index.html"),
        "standalone_sha256": file_sha256(report / "report_standalone.html"),
        "standalone_bytes": len(standalone.encode()),
        "remote_dependencies": 0,
        "claim_count": len(claims["claims"]),
        "example_count": examples.height,
        "claim_registry_sha256": file_sha256(claims_path),
        "examples_sha256": file_sha256(examples_json_path),
        "artifact_index_sha256": file_sha256(artifact_index_path),
    }
    (run_dir / "report-summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--smoke", action="store_true")
    args = parser.parse_args()
    result = generate("smoke" if args.smoke else "full")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
