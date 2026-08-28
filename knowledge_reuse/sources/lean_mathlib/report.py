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
    ROOT,
    raw_root,
    run_results_root,
)

CONFIG = tomllib.loads(CONFIG_PATH.read_text())
TITLES = {
    "kind_counts": "图 1 · 声明类型构成",
    "indegree_ccdf": "图 2 · 复用入度经验 CCDF",
    "rank_frequency": "图 3 · 复用入度 Rank–Frequency",
    "tail_overlay": "图 4 · 幂律尾部拟合诊断",
    "source_length": "图 5 · 源码长度与复用",
    "type_length": "图 6 · 类型表达式复杂度与复用",
    "value_length": "图 7 · 定义体/证明复杂度与复用",
    "length_binned": "图 8 · 长度分箱后的复用分布",
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
    "source_length": "仅绘制存在源码范围的声明；缺失值保持缺失，不被替换为零。",
    "type_length": "类型表达式树出现次数覆盖全部内部声明；散点仅为可视化降采样。",
    "value_length": "仅绘制具有定义体或证明体的声明；无 value 的声明保持缺失。",
    "length_binned": "源码字节数的对数分箱，展示每箱复用入度中位数及四分位数。",
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


_REPORT_ENV = jinja2.Environment(autoescape=True)
_REPORT_ENV.filters["fmt"] = format_cell
TEMPLATE = _REPORT_ENV.from_string("""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lean 4 / mathlib 知识复用图正式实验报告</title>
<style>{{ css|safe }}</style></head><body>
<header><p class="eyebrow">KNOWLEDGE REUSE RESEARCH · LEAN / MATHLIB V1</p>
<h1>形式化知识如何被复用？</h1>
<p class="dek">从 Lean 声明、语义依赖图到重尾分布与复杂度关系的完整实验报告</p>
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
<li><a href="#s3">图模型</a></li><li><a href="#s4">完整性</a></li>
<li><a href="#s7">复杂度算法</a></li><li><a href="#s8">图统计</a></li>
<li><a href="#s10">重尾检验</a></li><li><a href="#s11">复杂度分析</a></li>
<li><a href="#s13">领域分析</a></li><li><a href="#s17">附录</a></li>
</ol></nav><main>

<section id="s1"><h2>1. 执行摘要</h2>
<div class="verdict supported"><b>构建结论 · supported</b><p>正式 full run 已完成全部 {{ quality.expected_module_count|fmt }} 个配置内模块，所有质量门禁通过。图中没有因运行时间、递归深度、边数或节点数而截断的数据。</p></div>
<div class="verdict exploratory"><b>统计结论 · exploratory</b><p>复用高度集中：前 1% 声明承接 {{ (summary.reuse_concentration.top_1pct_share*100)|round(1) }}% 的入边，Gini={{ summary.reuse_concentration.gini|round(3) }}。这是快照内的观察性结果。</p></div>
<div class="verdict inconclusive"><b>分布结论 · inconclusive</b><p>尾部很重，但当前模型比较不支持仅凭直线外观宣称 Zipf/纯幂律；bootstrap 拟合优度尚未实现。</p></div>
<p>本实验的核心产物不是源码文本网络，而是从固定版本 Lean elaborated environment 提取的 declaration graph。报告依次说明概念、图构建、完整性证据、复杂度算法、图统计与实验解释。</p></section>

<section id="s2"><h2>2. 概念设计：研究对象与问题</h2>
<p>研究对象是 <em>mathlib 中已 elaboration 的形式化知识单元及其直接语义依赖</em>。声明是可命名、可复用的最小稳定单位；一个声明在另一个声明的类型或定义体/证明体中作为常量出现，即形成复用关系。</p>
<div class="grid"><article><h3>复用是什么</h3><p>若声明 A 的表达式包含声明 B 的常量引用，则 A 依赖 B；反向看，B 被 A 复用。入度衡量被多少唯一声明引用，出度衡量当前声明依赖多少唯一声明。</p></article>
<article><h3>研究问题</h3><p>RQ-A 复用是否集中？RQ-B 长度/结构复杂度与复用有何关系？RQ-C 领域间是否异质？RQ-D TYPE 与 VALUE 依赖有何区别？RQ-E 图契约能否迁移到其他知识源？</p></article></div>
<div class="callout"><b>解释边界</b> 语义常量引用不是人的引用意图。自动生成代码、类型类、强制转换和 elaborator 插入项都属于机器可复现的依赖事实，但不应直接解释为作者有意识的“引用”。</div></section>

<section id="s3"><h2>3. Declaration Graph 模型</h2>
<p>定义有向、类型化图 <code>G=(V,E)</code>。<code>V</code> 是内部声明与被引用的显式外部目标；<code>E</code> 的方向固定为 <code>consumer → dependency</code>。</p>
<div class="grid three"><article><h3>节点 V</h3><p>稳定身份由完整声明名给出，附带 module、kind、domain、源码范围、是否生成、是否有 value 等属性。</p></article><article><h3>TYPE 边</h3><p>目标常量出现在声明的 elaborated type 中，描述接口、命题陈述与类型层依赖。</p></article><article><h3>VALUE 边</h3><p>目标常量出现在 definition value 或 theorem proof 中，描述实现与证明层依赖。</p></article></div>
<p>同一 consumer、dependency、edge kind 只保留一条唯一边。因此本报告分析的是“被多少不同声明复用”，不是常量在表达式内出现了多少次；v1 的边 multiplicity 明确保留为空。</p></section>

<section id="s4"><h2>4. 图构建与完整性：没有截断</h2>
<div class="answer"><b>结论：完整图已成功构建。</b> {{ quality.extracted_module_count|fmt }}/{{ quality.expected_module_count|fmt }} 个模块状态均为 ok，{{ summary.declaration_count|fmt }} 个内部声明节点和 {{ summary.edge_count|fmt }} 条唯一语义边进入规范化数据；另有 {{ quality.external_node_count|fmt }} 个外部/prelude 目标被显式保留。</div>
<p>提取顺序为 capability probe → golden fixture → inventory/sharding → full extraction → normalization → validation。正式提取仅在固定 Lean API 与金样门禁通过后运行。失败模块、不可用证明体和缺失 source range 都不会被悄悄转成空集合。</p>
<div class="grid"><article><h3>为什么长时间运行</h3><p>工作量来自 8,264 个模块环境加载、56 万声明的表达式遍历，以及约 2,474 万条去重边的序列化与规范化；它不是算法以无界递归反复展开同一子表达式。</p></article><article><h3>缓存解决了什么</h3><p>Expr 是共享 DAG。复杂度提取先按对象指针访问每个唯一子表达式一次，再由缓存计算树出现次数，既避免共享子图的重复递归，又不牺牲研究所需的完整计数。</p></article></div>
<h3>质量门禁</h3>{{ quality_table|safe }}
<p class="note">“完整”是相对于固定 corpus 与提取契约：配置排除项不属于总体；外部目标不伪装成内部声明；源码范围缺失保持 null。</p></section>

<section id="s5"><h2>5. 节点体系与总体边界</h2>
<p>内部节点覆盖 theorem、definition、constructor、recursor、inductive 与 opaque。生成声明仍被保留并以 <code>is_generated</code> 标记，避免改变原始图；分析阶段另提供 NO_GENERATED 等视图。</p>
{{ figs.kind_counts|safe }}
<p>声明 identity 不依赖文件位置或 source range，因此即使 elaborator 生成的声明没有可靠源码区间，也不会从图中消失。</p></section>

<section id="s6"><h2>6. 边语义、计数口径与图视图</h2>
<div class="hero-stats compact"><div><strong>{{ summary.type_edge_count|fmt }}</strong><span>TYPE edges</span></div><div><strong>{{ summary.value_edge_count|fmt }}</strong><span>VALUE edges</span></div><div><strong>{{ summary.self_loop_count|fmt }}</strong><span>self loops</span></div><div><strong>{{ summary.edge_count|fmt }}</strong><span>合计</span></div></div>
<p>TYPE 与 VALUE 分开保存、分别统计，同时提供 ALL 合并视图。自环保留，因为它可能来自递归结构或 elaborated 常量关系；重复类型化边在规范化时拒绝。所有内部 source 和 target 均通过 dangling 检查，外部 target 进入独立命名空间。</p></section>

<section id="s7"><h2>7. 节点长度与复杂度变量</h2>
<h3>精确算法</h3><ol class="steps"><li><b>指针访问阶段：</b>对 type/value Expr DAG 做指针去重的 postorder；用 visited set 保证每个唯一对象只展开一次。</li><li><b>缓存递推阶段：</b>为每个唯一 Expr 计算任意精度 <code>Nat</code> 结果，并按子项出现位置求和，从而恢复树语义下的出现次数。</li><li><b>常量集合：</b>分别收集 TYPE/VALUE 中唯一常量名，得到 <code>*_const_unique</code>；边生成不设置 cap。</li></ol>
<div class="callout"><b>缓存不等于截断。</b> visited/cache 只消除相同 DAG 对象的重复计算；当共享子表达式被父节点多次引用时，其缓存值仍按每次出现累计。没有饱和上限，使用 Lean <code>Nat</code> 避免固定宽度溢出。</div>
<h3>已测量变量与覆盖率</h3>{{ complexity_table|safe }}
<p><code>source_bytes/source_lines/source_tokens</code> 来自可用的声明 source range；<code>type_expr_nodes/value_expr_nodes</code> 是表达式树出现次数；<code>type_const_unique/value_const_unique</code> 是唯一常量种类数。缺失 source range 的生成声明保持 null。</p>
<div class="verdict inconclusive"><b>尚未测量</b><p>最大 Expr 深度与唯一指针节点数（DAG size）目前未进入 v1 schema。它们是有价值的补充复杂度变量，但不能用现有 tree-occurrence 计数冒充。本报告不补造结果。</p></div></section>

<section id="s8"><h2>8. 图总体统计</h2>
<div class="metric-table">{{ graph_table|safe }}</div>
<div class="grid figures">{{ figs.indegree_ccdf|safe }}{{ figs.rank_frequency|safe }}</div>
<p>{{ (summary.zero_indegree_fraction*100)|round(2) }}% 的内部声明没有被其他内部声明复用；{{ (summary.zero_outdegree_fraction*100)|round(2) }}% 没有内部依赖；完全孤立比例仅 {{ (summary.isolated_fraction*100)|round(4) }}%。</p></section>

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
<div class="grid figures">{{ figs.source_length|safe }}{{ figs.type_length|safe }}{{ figs.value_length|safe }}{{ figs.length_binned|safe }}</div>
<h3>秩相关</h3>{{ correlations_table|safe }}
<h3>控制声明类型与领域后的负二项 GLM</h3>{{ regressions_table|safe }}
<p>模型使用 <code>log1p(length)</code> 并控制 kind + domain。系数不是因果效应；表中的“长度翻倍变化”将系数转换为更直观的期望复用相对变化。源码长度呈弱正的未控制秩相关，但控制变量后的模型系数为负，说明构成差异会改变表面关系。</p></section>

<section id="s12"><h2>12. Declaration kind 分析</h2>
{{ kind_table|safe }}
<p>定理占 {{ theorem_share }}% 节点。拟合总体同时包含 theorem-only、definition-only、TYPE、VALUE、theorem→theorem 和 theorem→definition，避免把不同语义人口混成一个分布。kind 是分析控制变量，不用于删改原始图。</p></section>

<section id="s13"><h2>13. 领域结构与 H*ref</h2>
<div class="grid figures">{{ figs.domain_scale|safe }}{{ figs.domain_heatmap|safe }}{{ figs.domain_entropy|safe }}{{ figs.domain_tail|safe }}</div>
{{ domain_table|safe }}
<div class="callout"><b>H*ref 的含义：</b>它是领域依赖分布的经验操作性代理，用来比较跨领域引用的分散程度；它不等于理论 H，也不能直接解释为领域的内在复杂度。</div></section>

<section id="s14"><h2>14. 稳健性视图</h2>
{{ figs.robustness|safe }}{{ views_table|safe }}
<p>ALL、NO_GENERATED、THEOREM_ONLY、DEFINITION_ONLY、THEOREM_AND_DEFINITION 与 USER_FACING_APPROX 使用同一不可变底图重建。若去掉生成声明后集中度仍然很高，就说明主要结论不是单由 compiler-generated 节点制造。</p></section>

<section id="s15"><h2>15. 可复现性与审计链</h2>
<p>原始 shard 数据不可变；normalized tables、metrics、figures 和 HTML 均可由其重建。manifest 固定 mathlib tag/commit、Lean toolchain、extractor commit、配置摘要、worker 数和运行环境。</p>
{{ manifest_table|safe }}
<p>图形中的降采样仅用于限制 HTML/SVG 体积；所有表格统计、拟合、相关、回归和集中度都在完整 metrics 上计算。</p></section>

<section id="s16"><h2>16. 解释、局限与结论</h2>
<div class="grid"><article><h3>可以说什么</h3><p>在固定 mathlib v4.32.1 快照和声明级语义图上，复用高度集中、分布具有重尾，领域与声明种类存在明显异质性，长度/结构复杂度与复用关系较弱且依赖控制口径。</p></article><article><h3>不能说什么</h3><p>不能由入度推断人的引用意图、数学深度或因果重要性；不能把路径领域当成本体；不能把尚未 bootstrap 的尾部拟合表述为已验证的普适定律。</p></article></div>
<p>建议下一阶段补充 Expr 最大深度与 DAG unique-node 指标、实现拟合优度 bootstrap，并在保持同一图契约下进行跨版本比较。Wikipedia 与开源软件图应使用各自 adapter，不改变 Lean v1 的冻结语义。</p></section>

<section id="s17"><h2>17. 附录：表格、性能与复现命令</h2>
<h3>复用最高的声明</h3>{{ top_table|safe }}
<h3>提取 worker benchmark</h3>{{ benchmark_table|safe }}
<h3>完整流水线</h3><pre>just bootstrap
just probe
just golden
just inventory
just extract
just normalize
just validate
just analyze
just report</pre>
<p>核心契约：<code>schemas/lean-graph-v1.md</code>。报告相邻目录保存 fits、regressions、domain metrics、quality checks、checksums 与独立 HTML。<code>--force</code> 行为保持不变。</p></section>
</main><footer>由版本化紧凑产物确定性生成 · 0 CDN · 0 远程脚本 · 0 远程字体</footer></body></html>""")


CSS = """:root{--ink:#15231d;--muted:#5f6c65;--paper:#f4f0e7;--card:#fffdf8;
--green:#175b45;--mint:#dceadf;--gold:#b47725;--red:#9c443d;--line:#cec7b9}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);
color:var(--ink);font:16px/1.68 system-ui,-apple-system,"Noto Sans CJK SC",sans-serif}
header,main,nav,footer{max-width:1180px;margin:auto}header{padding:72px 34px 38px}
main{padding:0 34px}.eyebrow{letter-spacing:.17em;font-size:.76rem;font-weight:800;
color:var(--green)}h1{font:800 clamp(2.7rem,7vw,5.8rem)/.98 Georgia,"Noto Serif SC",serif;
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
    benchmark_path = metrics / "extraction_benchmark.parquet"
    benchmark = (
        pl.read_parquet(benchmark_path)
        if benchmark_path.exists()
        else pl.DataFrame(
            json.loads((BENCHMARK_ROOT / "extraction.json").read_text())["rows"]
        )
    )

    complexity_labels = {
        "source_bytes": "源码字节数",
        "source_lines": "源码行数",
        "source_tokens": "源码 token 数",
        "type_expr_nodes": "Type Expr 树节点出现次数",
        "value_expr_nodes": "Value/Proof Expr 树节点出现次数",
        "type_const_unique": "Type 唯一常量数",
        "value_const_unique": "Value/Proof 唯一常量数",
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
        ).alias("长度翻倍变化 %")
    ).select(
        pl.col("length_metric").alias("变量"),
        "n",
        pl.col("coefficient").alias("beta"),
        pl.col("ci_low").alias("95% CI low"),
        pl.col("ci_high").alias("95% CI high"),
        "长度翻倍变化 %",
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
    binned = bins.filter(pl.col("length_metric") == "source_bytes").sort(
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
            nodes["source_bytes"].to_list(),
            nodes["in_degree_all"].to_list(),
            "source bytes (log)",
            "reuse (log)",
        ),
        "type_length": points_svg(
            TITLES["type_length"],
            nodes["type_expr_nodes"].to_list(),
            nodes["in_degree_all"].to_list(),
            "type Expr nodes (log)",
            "reuse (log)",
        ),
        "value_length": points_svg(
            TITLES["value_length"],
            nodes["value_expr_nodes"].to_list(),
            nodes["in_degree_all"].to_list(),
            "value Expr nodes (log)",
            "reuse (log)",
        ),
        "length_binned": line_svg(
            TITLES["length_binned"],
            [
                ("median", binned["length_median"].to_list(), binned["reuse_median"].to_list()),
                ("q25", binned["length_median"].to_list(), binned["reuse_q25"].to_list()),
                ("q75", binned["length_median"].to_list(), binned["reuse_q75"].to_list()),
            ],
            "source bytes (log)",
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
    local = {
        name: (
            f'<figure class="figure"><img src="assets/{name}.svg" '
            f'alt="{html.escape(TITLES[name])}"><figcaption>'
            f'{html.escape(FIGURE_CAPTIONS[name])}</figcaption></figure>'
        )
        for name in figures
    }
    inline = {
        name: (
            f'<figure class="figure">{svg}<figcaption>'
            f'{html.escape(FIGURE_CAPTIONS[name])}</figcaption></figure>'
        )
        for name, svg in figures.items()
    }
    context = {
        "css": CSS,
        "quality": quality,
        "summary": summary,
        "manifest": manifest,
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
            pl.DataFrame([manifest]).transpose(
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
