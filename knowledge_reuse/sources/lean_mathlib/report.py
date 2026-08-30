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
    "domain_tail": "图 13 · 领域 Gini 与尾部参数",
    "robustness": "图 14 · 不同声明视图的稳健性",
}

FIGURE_CAPTIONS = {
    "kind_counts": "按 Lean 声明种类统计。定理占主体，但构造器、归纳类型和递归器仍作为独立节点保留。",
    "indegree_ccdf": "仅使用正入度节点；双对数坐标用于观察尾部，曲线形状本身不构成幂律证据。",
    "rank_frequency": "声明按总入度降序排列；绘图时确定性降采样，不改变用于统计检验的完整数据。",
    "tail_overlay": "经验 CCDF 与估计幂律尾部的诊断性叠加；模型优劣以似然比较而非视觉判断为准。",
    "source_length": "仅绘制存在源码范围的声明；这里的 Token 是明确规则的源码代理量，不是 Lean lexer token。",
    "type_length": "类型表达式实际共享 DAG 的唯一指针节点数；散点仅为可视化降采样。",
    "value_length": "仅绘制具有定义体或证明体的声明；null 不被替换为零。",
    "length_binned": "Value 展开倍数 T/U 的对数分箱，展示每箱复用入度中位数及四分位数。",
    "lorenz": "横轴为声明累计比例，纵轴为收到的复用边累计比例；对角线代表完全均匀。",
    "domain_scale": "领域由模块路径映射得到；它是可复现的工程分组，不等同于数学本体分类。",
    "domain_heatmap": "行是依赖发起领域，列是被依赖领域；颜色表示行内依赖份额。",
    "domain_entropy": "H*ref 是跨领域引用多样性的经验操作性代理，不是理论信息熵 H。",
    "domain_tail": "仅包含可估计尾部参数的领域；缺失 alpha 不被替换为零。",
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
    summary: dict[str, Any], quality: dict[str, Any], fits: pl.DataFrame
) -> dict[str, Any]:
    all_fit = fits.filter(pl.col("population") == "all_declarations").row(
        0, named=True
    )
    complete = quality["passed"] and quality["extraction_completeness"] == 1
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
                "claim_id": "reuse.concentration",
                "status": "supported",
                "text": (
                    f"复用高度集中：Top 1% 承接 "
                    f"{summary['reuse_concentration']['top_1pct_share']:.1%} 的唯一入边，"
                    f"Gini={summary['reuse_concentration']['gini']:.3f}。"
                ),
                "evidence": [
                    "metrics/summary.json#/reuse_concentration",
                    "metrics/view_metrics.parquet",
                ],
                "scope": "ALL internal declarations",
                "caveat": "入度集中不等于数学重要性或人的引用意图。",
            },
            {
                "claim_id": "tail.model_comparison",
                "status": "inconclusive",
                "text": (
                    "入度分布具有重尾，但替代模型比较不支持仅凭图形宣称"
                    "纯幂律或 Zipf 定律。"
                ),
                "evidence": ["metrics/powerlaw_fits.parquet#population=all_declarations"],
                "scope": f"positive indegree population; tail_n={all_fit['tail_n']:,}",
                "caveat": f"goodness-of-fit bootstrap: {all_fit['bootstrap_status']}",
            },
            {
                "claim_id": "complexity.association",
                "status": "exploratory",
                "text": "源码、DAG、深度、展开树与依赖广度对复用呈现不同的关联强度，结论依赖复杂度定义与控制项。",
                "evidence": [
                    "metrics/length_correlations.parquet",
                    "metrics/regressions.parquet",
                ],
                "scope": "source/type/value metrics with available observations",
                "caveat": "观察性关联不是因果效应。",
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
<p class="dek">从真实声明与语义边出发，逐步建立可审计的图统计、复杂度分析和研究结论</p>
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
<li><a href="#s3">研究问题</a></li><li><a href="#s4">Corpus</a></li>
<li><a href="#s5">图语义</a></li><li><a href="#s6">完整性</a></li>
<li><a href="#s7">复杂度</a></li><li><a href="#s8">图统计</a></li>
<li><a href="#s9">集中度</a></li><li><a href="#s10">重尾检验</a></li>
<li><a href="#s11">复杂度与复用</a></li><li><a href="#s12">Kind/Edge</a></li>
<li><a href="#s13">领域</a></li><li><a href="#s14">稳健性</a></li>
<li><a href="#s15">跨系统</a></li><li><a href="#s16">结论</a></li>
<li><a href="#s17">附录</a></li>
</ol></nav><main>

<section id="s1"><h2>1. 执行摘要</h2>
<p>以下结论来自机器可读 claim registry。每条结论都标明证据等级、总体范围和限制。</p>
{% for claim in claims.claims %}<article class="claim {{ claim.status }}" id="{{ claim.claim_id }}">
<div><span class="badge">{{ claim.status }}</span><b>{{ claim.text }}</b></div>
<p><strong>范围：</strong>{{ claim.scope }}　<strong>限制：</strong>{{ claim.caveat }}</p>
<small>Evidence: {{ claim.evidence|join(' · ') }}</small></article>{% endfor %}
<p class="bridge">下面不直接跳到总体图形。我们先用真实 mathlib declaration 建立 node、value 和 reuse 的直觉，再说明这些单例如何扩展成全库统计。</p></section>

<section id="s2"><h2>2. 概念设计与研究对象</h2>
<p>研究对象是 <em>mathlib 中已 elaboration 的形式化知识单元及其直接语义依赖</em>。Lean 把一条定理、定义、公理、归纳类型、构造器或递归器登记为一个有完整名称的 declaration；本研究把配置语料内的每个 declaration 作为一个 node。Node 不是源码中的一行，也不是表达式树中的一个小括号。</p>
<div class="grid"><article><h3>Node 有什么</h3><p>每个 node 一定有 <b>name</b>、<b>kind</b> 和 <b>type</b>。type 说明“它是什么”；如果环境还公开定义体或证明体，则另有 <b>value</b>，说明“它怎样被构造或证明”。源码范围是附加观测，缺失不会删除 node。</p></article>
<article><h3>Node value 为什么会是 null</h3><p>判定规则只有一个：固定环境的 <code>getDeclarationValue?</code> 返回 none 时，<code>has_value=false</code>，全部 value-complexity 记为 null。null 表示“没有可观测 value”，不是“复杂度为零”。归纳类型和构造器等常出现这种情况；实际分布见下表。</p></article>
<article><h3>Reuse 是什么</h3><p>若 A 的 elaborated type 或 value 包含常量 B，则 A → B。B 的入度统计有多少不同声明复用它；A 的出度描述自身直接依赖负担。</p></article>
<article><h3>Complexity 是什么</h3><p>复杂度不是一个数字。本研究分别观察源码表面规模、表达式 DAG 的实际结构、最大嵌套深度、共享内容完全展开后的规模，以及引用了多少不同常量。它们回答不同问题，不能互相替代。</p></article></div>
<h3>Value 可观测性按声明类型分布</h3>{{ value_availability_table|safe }}
<p class="callout"><b>null 对复用实验的影响：</b>该 node 仍进入总体图；它的 type 边、别人指向它的入边和复用入度都可分析。只有它自身的 VALUE 出边与 value/proof 复杂度不可观测，因此相关分析按有效样本数排除，而不是补 0。若某类 node 的 null 比例很高，跨 kind 比较必须分层或控制 kind。</p>
<h3>真实节点证据</h3>{{ node_examples_table|safe }}
<div class="callout"><b>解释边界</b> 语义常量引用不是人的引用意图。自动生成代码、类型类、强制转换和 elaborator 插入项都属于机器可复现的依赖事实，但不应直接解释为作者有意识的“引用”。</div></section>

<section id="s3"><h2>3. 研究问题与判断路径</h2>
<table><thead><tr><th>RQ</th><th>问题</th><th>总体与方法</th><th>允许的结论</th></tr></thead><tbody>
<tr><td>A</td><td>复用是否集中/重尾？</td><td>ALL/TYPE/VALUE；Gini、CCDF、模型比较</td><td>集中度可 supported；幂律必须经过比较</td></tr>
<tr><td>B</td><td>不同层次复杂度与复用关系？</td><td>source、DAG、depth、tree expansion、constant breadth；Spearman、分箱、NB GLM</td><td>比较指标敏感性；观察性关联不作因果解释</td></tr>
<tr><td>C</td><td>领域是否异质？</td><td>路径领域；matrix、Gini、tail、H*ref</td><td>比较工程 taxonomy，不推断数学本体</td></tr>
<tr><td>D</td><td>边/节点语义是否不同？</td><td>kind 与 TYPE/VALUE 子图</td><td>分层描述，不混合机制</td></tr>
<tr><td>E</td><td>能否跨系统比较？</td><td>core graph projection</td><td>比较 core metric，不混同 native units</td></tr>
</tbody></table></section>

<section id="s4"><h2>4. Corpus 与 Snapshot</h2>
<p>本报告绑定 <code>{{ manifest.mathlib_tag }}</code>、完整 commit <code>{{ manifest.mathlib_commit }}</code> 和 toolchain <code>{{ manifest.lean_toolchain }}</code>。总体由 <code>{{ config.corpus_glob }}</code> 与版本化 exclusions 共同定义。</p>
<h3>配置化排除规则</h3>{{ exclusions_table|safe }}
<p class="note">“100% 完整”只指 configured corpus；不包含排除目录、其他 Lean package 或历史版本。</p></section>

<section id="s5"><h2>5. 图构建语义：从真实边到 Graph</h2>
<p>定义 <code>G=(V,E)</code>，方向固定为 <code>consumer → dependency</code>。TYPE 表示 target constant 出现在 type/statement；VALUE 表示它出现在 definition body 或 proof。</p>
<h3>两个不同语义的真实关系</h3>{{ edge_examples_table|safe }}
<div class="grid"><article><h3>TYPE 示例如何进入图</h3><p><code>padicValRat.of_nat</code> 的 elaborated type 包含 <code>padicValNat</code>，因此规范化为一条 theorem→definition TYPE edge。</p></article><article><h3>VALUE 示例如何进入图</h3><p><code>constantCoeff_xInTermsOfW</code> 的 proof/value 包含 <code>map_pow</code>，因此规范化为 theorem→theorem VALUE edge。</p></article></div>
<p class="bridge">单条边只证明一个依赖实例存在。将所有 declaration 的常量引用按相同规则提取、确定性编号并对 `(src,dst,type)` 去重，才得到用于总体分析的完整图。</p></section>

<section id="s6"><h2>6. 研究范围与观测完整性</h2>
<div class="answer"><b>本报告覆盖配置语料的全部 {{ quality.expected_module_count|fmt }} 个模块。</b>共观测 {{ summary.declaration_count|fmt }} 个内部 declaration、{{ quality.external_node_count|fmt }} 个语料外依赖目标和 {{ summary.edge_count|fmt }} 条唯一类型化边。</div>
<p>“完整”只针对第 4 节定义的固定 snapshot 与 configured corpus。语料外常量作为 external target 保留；源码范围和 value 的缺失保持 null。后续每个复杂度统计都报告非空样本数与覆盖率，使读者能区分“零”与“未观测”。</p></section>

<section id="s7"><h2>7. 节点长度与复杂度变量</h2>
<p>一个 node 的 type 与可观测 value/proof 各自都是 Lean Expr。下面把“复杂度”拆成可以独立计算、独立解释的层次。</p>
<h3>7.1 源码表面复杂度：bytes、lines 与 Token 代理量</h3>
<p><b>bytes</b> 是声明源码片段的 UTF-8 字节数；<b>lines</b> 是覆盖的源码行数。<b>Token 代理量</b>采用确定性正则规则：以 ASCII 英文字母或下划线开头、后接 ASCII 英文字母、数字、下划线或撇号的连续串算 1 个；连续数字算 1 个；其余每个非空白字符各算 1 个；空格和换行不计。</p>
<pre>theorem addOne (n : Nat) : n + 1 = Nat.succ n := by rfl
→ theorem | addOne | ( | n | : | Nat | ) | : | n | + | 1 | = |
  Nat | . | succ | n | : | = | by | rfl     （共 20 个）</pre>
<p class="note">因此 <code>:=</code> 算两个、<code>Nat.succ</code> 算三个。它是便于跨声明复现的源码词法代理，不是 Lean lexer 的精确 token；注释或字符串内部字符仍按同一规则计数。报告据此只讨论“表面规模”，不把它冒充证明语义复杂度。</p>
<h3>7.2 表达式结构复杂度：U、A、D、T</h3>
<p>令 <code>children(x)</code> 是 Expr x 的直接子表达式位置。对根表达式 E：</p>
<ul><li><b>唯一 DAG 节点 U</b>：从 E 可到达的不同 Expr 对象个数，近似回答“实际存了多少结构”。</li><li><b>DAG arcs A</b>：所有唯一节点的 child position 总数；同一 child 被引用两次就有两条 arc。</li><li><b>最大深度 D</b>：叶子深度为 1；非叶子为 <code>1 + max(child depth)</code>，回答“最长嵌套链有多深”。</li><li><b>展开树出现次数 T</b>：叶子为 1；非叶子为 <code>1 + sum(T(child))</code>。共享 child 每被引用一次就贡献一次，回答“若把共享完全展开，树有多大”。</li><li><b>展开倍数 T/U</b>：比较概念展开规模与实际共享结构；越大表示共享重复越强。</li></ul>
<h3>可手算的共享 DAG</h3><pre class="dag">        parent
        /    \
     shared  shared
        |
       leaf</pre>
<p>这里只有 3 个不同对象，所以 U=3；parent 有两个 child position，shared 有一个，所以 A=3；最长路径 parent→shared→leaf，所以 D=3；完全展开时 parent 计 1，两个 shared 分支各计 2，所以 T=5，展开倍数 T/U=5/3。这个例子说明 T 很大时可能主要反映重复展开，而 U、A、D 描述的是另外三种结构性质。</p>
<p>计算时先遍历每个唯一节点及其 arcs，再按上述递推式汇总，所以时间复杂度为 <code>O(U+A)</code>、辅助空间为 <code>O(U)</code>。这是算法定义，不把 T 解释成实际运行时间。</p>
<p class="note">U 是固定 Lean 版本与载入环境中的指针共享测量，适合本 snapshot 内比较；跨 Lean 版本时必须重新测量，不能把它当成永恒不变的语义属性。</p>
<h3>7.3 依赖广度</h3><p><b>unique constants</b> 统计 type 或 value 中出现了多少个不同的命名常量。重复调用同一常量只计一次，所以它衡量依赖“种类”的广度，不衡量调用次数。</p>
<h3>真实节点复杂度：从 small 到 high</h3>{{ complexity_examples_table|safe }}
<p><code>CategoryTheory.Limits.colimitLimitToLimitColimit_surjective</code> 的 value 展开树 T 为 {{ high_example.value_expr_tree_occurrences|fmt }}，但实际 DAG 唯一节点 U 为 {{ high_example.value_expr_unique_ptr_nodes|fmt }}，展开倍数为 {{ high_example.value_expr_expansion_factor|round(2) }}。三个数回答不同问题，不能单独称为“工作量”。</p>
<h3>全部测量变量、覆盖率与分布</h3>{{ complexity_table|safe }}</section>

<section id="s8"><h2>8. 图总体统计</h2>
<div class="metric-table">{{ graph_table|safe }}</div>
<h3>从 incoming edges 到 reuse indegree</h3><p>下面是目标 <code>DFunLike.coe</code> 的 5 条确定性展示边。相同 source 的 TYPE 与 VALUE 是两条 typed edges，但 ALL unique consumer 只计一次。</p>{{ reuse_examples_table|safe }}
<p>该 target 的完整 ALL indegree 为 {{ reuse_target_degree|fmt }}；表中 5 行只是解释计数规则，不是统计样本。</p>
<div class="grid figures">{{ figs.indegree_ccdf|safe }}{{ figs.rank_frequency|safe }}</div>
<p class="bridge">从一个 target 的入度扩展到全部 {{ summary.declaration_count|fmt }} 个节点，得到 CCDF 与 rank-frequency：{{ (summary.zero_indegree_fraction*100)|round(2) }}% 入度为零，完全孤立比例 {{ (summary.isolated_fraction*100)|round(4) }}%。</p></section>

<section id="s9"><h2>9. 复用集中度</h2>
<div class="hero-stats compact"><div><strong>{{ summary.reuse_concentration.gini|round(3) }}</strong><span>Gini</span></div><div><strong>{{ (summary.reuse_concentration.top_1pct_share*100)|round(1) }}%</strong><span>Top 1%</span></div><div><strong>{{ (summary.reuse_concentration.top_5pct_share*100)|round(1) }}%</strong><span>Top 5%</span></div><div><strong>{{ (summary.reuse_concentration.top_10pct_share*100)|round(1) }}%</strong><span>Top 10%</span></div></div>
{{ figs.lorenz|safe }}
<p>高 Gini 与陡峭 Lorenz 曲线共同表明，形式化库的复用不是均匀分散的：少数基础声明承接了大部分依赖。但集中度不自动等价于“重要性”，更不代表教学价值或证明难度。</p></section>

<section id="s10"><h2>10. 重尾模型比较</h2>
{{ figs.tail_overlay|safe }}
{{ fits_table|safe }}
<p>全体正入度声明的拟合参数为 alpha={{ all_fit.alpha }}, xmin={{ all_fit.xmin }}, KS={{ all_fit.ks }}。相对 lognormal 与 truncated power law 的对数似然比为负且达到显著性，说明替代模型在当前比较中更受支持。因此正确结论是“存在重尾和强集中”，而不是“已证实 Zipf 定律”。</p>
<p class="note">bootstrap 状态为 <code>{{ all_fit.bootstrap_status }}</code>，所以不能报告基于 bootstrap 的绝对拟合优度 p 值。</p></section>

<section id="s11"><h2>11. 长度/复杂度与复用</h2>
<p>本节不寻找一个“正确的复杂度数字”，而是比较结论对复杂度定义是否敏感。结构很小的 <code>Set</code> 可以有很高复用，展开树巨大的 theorem 也不一定成为最高复用节点，因此必须进行总体统计并控制 kind/domain。</p>
{{ complexity_compare_table|safe }}
<div class="grid figures">{{ figs.source_length|safe }}{{ figs.type_length|safe }}{{ figs.value_length|safe }}{{ figs.length_binned|safe }}</div>
<h3>秩相关</h3>{{ correlations_table|safe }}
<h3>控制声明类型与领域后的负二项 GLM</h3>{{ regressions_table|safe }}
<p>Spearman rho 比较排序关系，不要求线性；对数分箱检查趋势是否被少量极端值推动。负二项模型以复用入度为计数响应，使用 <code>log1p(complexity)</code> 并控制 kind + domain。表中的“复杂度翻倍变化”是期望复用的相对变化。所有结果都是观察性关联，不是“复杂度导致复用”的因果效应。</p>
<div class="callout"><b>如何读多层结果：</b>若 T 的关联明显强于 U/A/D，可能是共享展开倍数在起作用；若 U 与 A 接近而 D 很弱，可能是总体结构规模而非最长嵌套链相关；若源码 Token 与 Expr 指标方向不同，说明短源码也可能 elaboration 成复杂对象。必须以表中实际系数、区间和 n 为准。</div></section>

<section id="s12"><h2>12. Node kind 与 Edge semantics</h2>
{{ figs.kind_counts|safe }}{{ kind_table|safe }}
<p>定理占 {{ theorem_share }}% 节点。前述 VALUE theorem→theorem 与 TYPE theorem→definition 说明不同边机制必须分层；拟合总体也分别包含 theorem-only、definition-only、TYPE、VALUE、theorem→theorem 和 theorem→definition。</p>
<p>完整 extraction 保留 generated/internal declarations；kind 只用于派生视图和控制变量，不改写底图。</p></section>

<section id="s13"><h2>13. 领域结构与 H*ref</h2>
<p>每条 src_domain→dst_domain 边使 dependency matrix 对应 cell 加 1。下面用两条跨领域边和一条领域内边展示累加规则。</p>{{ domain_examples_table|safe }}
<div class="grid figures">{{ figs.domain_scale|safe }}{{ figs.domain_heatmap|safe }}{{ figs.domain_entropy|safe }}{{ figs.domain_tail|safe }}</div>
{{ domain_table|safe }}
<div class="callout"><b>H*ref 的含义：</b>它是领域依赖分布的经验操作性代理，用来比较跨领域引用的分散程度；它不等于理论 H，也不能直接解释为领域的内在复杂度。</div></section>

<section id="s14"><h2>14. 稳健性视图</h2>
{{ figs.robustness|safe }}{{ views_table|safe }}
<p>ALL、NO_GENERATED、THEOREM_ONLY、DEFINITION_ONLY、THEOREM_AND_DEFINITION 与 USER_FACING_APPROX 使用同一不可变底图重建。若去掉生成声明后集中度仍然很高，就说明主要结论不是单由 compiler-generated 节点制造。</p></section>

<section id="s15"><h2>15. 跨系统解释</h2>
<table><thead><tr><th>通用概念</th><th>Lean</th><th>Wikipedia</th><th>Software</th></tr></thead><tbody>
<tr><td>node</td><td>declaration</td><td>page/article</td><td>固定粒度的 function/module/package</td></tr>
<tr><td>edge</td><td>TYPE/VALUE reference</td><td>hyperlink/citation</td><td>call/import/dependency</td></tr>
<tr><td>reuse</td><td>unique consumer indegree</td><td>unique linking pages</td><td>unique callers/dependents</td></tr>
<tr><td>native complexity</td><td>source proxy；Expr U/A/D/T；unique constants</td><td>wikitext/token/link/section structure</td><td>source token；AST/call depth/cyclomatic structure</td></tr>
</tbody></table><p>indegree、Gini、rank-frequency 可通过 core projection 比较；Expr nodes、wikitext bytes 与 AST nodes 不是等价单位，不能直接比较原值。</p></section>

<section id="s16"><h2>16. 解释、局限与结论</h2>
<div class="grid"><article><h3>可以说什么</h3><p>在固定 mathlib v4.32.1 快照和声明级语义图上，复用高度集中、分布具有重尾，领域与声明种类存在明显异质性；不同复杂度层次与复用的关联必须分别报告。</p></article><article><h3>不能说什么</h3><p>不能由入度推断人的引用意图、数学深度或因果重要性；不能把路径领域当成本体；不能把尚未 bootstrap 的尾部拟合表述为已验证的普适定律。</p></article></div>
<p>下一阶段可实现拟合优度 bootstrap，并在保持同一图契约下进行跨版本比较。Wikipedia 与开源软件图应使用各自 adapter 和本地复杂度单位，再通过 indegree、集中度等 core metric 比较。</p></section>

<section id="s17"><h2>17. 附录：证据索引</h2>
<p>以下表格供研究人员从报告结论回到机器可读证据。复现命令、运行性能与执行日志保留在仓库文档和结果目录，不进入研究叙事。</p>
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
    regressions = pl.read_parquet(metrics / "regressions.parquet")
    domains = pl.read_parquet(metrics / "domain_metrics.parquet")
    matrix = pl.read_parquet(tables / "domain_matrix.parquet")
    views = pl.read_parquet(metrics / "view_metrics.parquet")
    bins = pl.read_parquet(metrics / "length_binned.parquet")
    value_availability = pl.read_parquet(metrics / "value_availability.parquet")
    examples_path = tables / "report_examples.parquet"
    examples = pl.read_parquet(examples_path)
    claims = build_claim_registry(summary, quality, fits)
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
        metrics / "regressions.parquet",
        metrics / "domain_metrics.parquet",
        metrics / "view_metrics.parquet",
        metrics / "length_binned.parquet",
        metrics / "length_correlations.parquet",
        metrics / "value_availability.parquet",
        tables / "top_reuse.csv",
        tables / "domain_matrix.parquet",
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
    positive = sorted([value for value in degree if value > 0])
    ccdf_x = sorted(set(positive))
    ccdf_y = [
        sum(value >= x for value in positive) / len(positive) for x in ccdf_x
    ] if positive else []
    lorenz_values = sorted(degree)
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
            [("all", list(range(1, len(degree) + 1)), degree)],
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
        "domain_heatmap": heatmap_svg(matrix),
        "domain_entropy": bar_svg(
            TITLES["domain_entropy"],
            top_domains["domain"].to_list(),
            top_domains["reference_entropy_proxy"].to_list(),
            "H*ref",
        ),
        "domain_tail": points_svg(
            TITLES["domain_tail"],
            domains["gini"].to_list(),
            domains["alpha"].to_list(),
            "Gini",
            "tail alpha",
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
        "rank_frequency": f"n_total={nodes.height:,}；n_positive={len(positive):,}；折线显示≤700点。",
        "tail_overlay": f"population=indegree≥xmin；tail_n={all_fit['tail_n'][0]:,}；折线显示≤700点。",
        "source_length": f"n_total={nodes.height:,}；metric n_valid={source_valid:,}；positive plotted population={source_plotted:,}；显示≤1,600点。",
        "type_length": f"n_total=n_valid={nodes.height:,}；positive plotted population={type_plotted:,}；显示≤1,600点。",
        "value_length": f"n_total={nodes.height:,}；metric n_valid={value_valid:,}；positive plotted population={value_plotted:,}；显示≤1,600点。",
        "length_binned": f"value expansion n_valid={value_valid:,}；分箱统计使用全部有效值。",
        "lorenz": f"population=ALL；n_total={nodes.height:,}；折线显示≤700点。",
        "domain_scale": f"population=top domains；展示 {top_domains.height} 个领域。",
        "domain_heatmap": f"population=internal typed edges；n={matrix['edge_count'].sum():,}。",
        "domain_entropy": f"population=top domains；展示 {top_domains.height} 个领域。",
        "domain_tail": f"population=domains with fitted alpha；n_valid={domains['alpha'].drop_nulls().len()}。",
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
    context = {
        "css": CSS,
        "quality": quality,
        "summary": summary,
        "manifest": manifest,
        "config": CONFIG,
        "claims": claims,
        "high_example": high_example,
        "reuse_target_degree": reuse_target_degree,
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
            fits.select(
                "population",
                "n",
                "tail_n",
                "xmin",
                "alpha",
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
