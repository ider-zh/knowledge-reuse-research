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


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "configs" / "experiment-v1.toml"
CONFIG = tomllib.loads(CONFIG_PATH.read_text())
TITLES = {
    "kind_counts": "Declaration counts by kind",
    "indegree_ccdf": "Reuse indegree complementary CDF",
    "rank_frequency": "Reuse rank-frequency",
    "tail_overlay": "Power-law fitted-tail diagnostic",
    "source_length": "Source length vs reuse",
    "type_length": "Type Expr size vs reuse",
    "value_length": "Value/proof Expr size vs reuse",
    "length_binned": "Log-binned reuse vs length",
    "lorenz": "Lorenz curve of reuse",
    "domain_scale": "Top domains by node count",
    "domain_heatmap": "Domain-to-domain dependency shares",
    "domain_entropy": "Per-domain H*ref operational proxy",
    "domain_tail": "Per-domain alpha and Gini",
    "robustness": "Robustness: all vs no-generated declarations",
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
    x_values: list[float],
    y_values: list[float],
    x_label: str,
    y_label: str,
    log_x: bool = True,
    log_y: bool = True,
) -> str:
    pairs = [
        (x, y)
        for x, y in zip(x_values, y_values, strict=True)
        if x > 0 and (y > 0 or not log_y)
    ]
    if len(pairs) > 2500:
        pairs = pairs[:: math.ceil(len(pairs) / 2500)]
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
    all_x = [x for _, xs, _ in series for x in xs if x > 0 or not log_x]
    all_y = [y for _, _, ys in series for y in ys if y > 0 or not log_y]
    sx, sy = scale(all_x, 78, 730, log_x), scale(all_y, 365, 60, log_y)
    colors = ["#386cb0", "#e6550d", "#31a354", "#756bb1"]
    body = axes(x_label, y_label)
    for index, (label, xs, ys) in enumerate(series):
        points = " ".join(
            f"{sx(x):.2f},{sy(y):.2f}"
            for x, y in zip(xs, ys, strict=True)
            if (x > 0 or not log_x) and (y > 0 or not log_y)
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


def render_table(frame: pl.DataFrame, limit: int = 20) -> str:
    frame = frame.head(limit)
    headings = "".join(f"<th>{html.escape(column)}</th>" for column in frame.columns)
    rows = []
    for row in frame.iter_rows():
        cells = "".join(f"<td>{html.escape(str(value))}</td>" for value in row)
        rows.append(f"<tr>{cells}</tr>")
    return f"<table><thead><tr>{headings}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def run_manifest(run_kind: str) -> dict[str, Any]:
    raw_path = (
        ROOT / "data" / "raw" / CONFIG["snapshot_id"] / run_kind / "manifest.json"
    )
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
    (ROOT / "results" / "run-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    )
    return manifest


TEMPLATE = jinja2.Template("""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Lean 4 / mathlib Reuse Graph Experiment</title>
<style>{{ css }}</style></head><body>
<header><p class="eyebrow">LEAN 4 / MATHLIB REUSE GRAPH</p>
<h1>How is formal knowledge reused?</h1>
<div class="status {{ 'ok' if quality.passed else 'bad' }}">
<b>{{ 'COMPLETE' if quality.extraction_completeness == 1 else 'INCOMPLETE' }}</b>
 · {{ quality.extracted_module_count }}/{{ quality.expected_module_count }} modules
 · {{ manifest.mathlib_tag }} · {{ manifest.mathlib_commit[:12] }}</div>
<p>{{ summary.declaration_count }} declarations and {{ summary.edge_count }} unique
typed semantic edges. Generated from pinned elaborated Lean environments.</p></header><main>
<section><h2>1. Executive Summary</h2><ul>
<li><b>supported</b> — extraction completeness is
{{ (quality.extraction_completeness*100)|round(2) }}%; validation gates
{{ 'passed' if quality.passed else 'did not pass' }}.</li>
<li><b>exploratory</b> — the top 1% receives
{{ (summary.reuse_concentration.top_1pct_share*100)|round(1) }}% of reuse edges;
Gini={{ summary.reuse_concentration.gini|round(3) }}.</li>
<li><b>inconclusive</b> — fitted alternatives do not establish a Zipf law from
plot shape alone.</li>
<li><b>exploratory</b> — length associations are observational and
snapshot-specific.</li></ul></section>
<section><h2>2. Research Questions &amp; Hypotheses</h2>
<p>RQ4-A reuse concentration; RQ4-B length versus reuse; RQ4-C domain
heterogeneity; RQ4-D TYPE versus VALUE semantics; RQ4-E a portable graph contract.</p></section>
<section><h2>3. Reproducibility Manifest</h2>{{ manifest_table|safe }}</section>
<section><h2>4. Corpus Definition</h2><p>Configured corpus:
<code>Mathlib/**/*.lean</code>. Archive, tests, benchmarks, and Counterexamples are
configurable exclusions. Inventory: {{ quality.expected_module_count }} modules.</p></section>
<section><h2>5. Lean Extraction Semantics</h2><p>A node is an elaborated
declaration. Edges point consumer → dependency and are typed TYPE or VALUE.
Private theorem bodies use pinned-version <code>import all</code>, verified by the
capability probe and exact golden gate. Source ranges do not define identity.</p></section>
<section><h2>6. Data Quality &amp; Completeness</h2>{{ quality_table|safe }}
<p>Nulls remain null. External/prelude targets are explicit.</p></section>
<section><h2>7. Graph Overview</h2>{{ figs.kind_counts|safe }}
{{ figs.indegree_ccdf|safe }}<p class="caption">The CCDF is empirical, not a
fitted-law conclusion.</p></section>
<section><h2>8. Reuse Rank-Frequency</h2>{{ figs.rank_frequency|safe }}
{{ figs.tail_overlay|safe }}</section>
<section><h2>9. Heavy-tail Model Comparison</h2>{{ fits_table|safe }}
<p>Likelihood comparisons cover lognormal and truncated alternatives. Bootstrap
status explicitly records whether goodness-of-fit bootstrap was implemented.</p></section>
<section><h2>10. Length vs Reuse</h2>{{ figs.source_length|safe }}
{{ figs.type_length|safe }}{{ figs.value_length|safe }}
{{ figs.length_binned|safe }}{{ regressions_table|safe }}
<p class="caption">Models include 95% confidence intervals and kind/domain controls.</p></section>
<section><h2>11. Declaration-kind Analysis</h2><p>Population fits separately cover
theorem→theorem and theorem→definition reuse. TYPE and VALUE stay distinct.</p></section>
<section><h2>12. Domain Analysis</h2>{{ figs.domain_scale|safe }}
{{ figs.domain_heatmap|safe }}{{ figs.domain_entropy|safe }}
{{ figs.domain_tail|safe }}{{ domain_table|safe }}
<p class="caption"><b>H*ref is an empirical operational proxy, not theoretical H.</b></p></section>
<section><h2>13. Robustness Checks</h2>{{ figs.lorenz|safe }}
{{ figs.robustness|safe }}{{ views_table|safe }}
<p>Views include ALL, NO_GENERATED, theorem-only, definition-only,
theorem-and-definition, and user-facing approximation. Multiplicity is null in v1.</p></section>
<section><h2>14. Interpretation relative to Veldhuizen</h2><p>This is a conceptual
replication on an elaborated declaration graph, with TYPE/VALUE and domain
extensions. It does not identify human citation intent. H*ref ≠ theoretical H.</p></section>
<section><h2>15. Limitations</h2><p>Automation, coercions, typeclasses, and generated
references differ from human-visible citations. Some generated declarations lack
source ranges. Path domains are coarse. Statistical results are observational.</p></section>
<section><h2>16. Conclusions &amp; Next Experiments</h2><p>Use this pinned snapshot as
the reproducible baseline. Next: cross-version comparisons, bootstrap
goodness-of-fit, and attribution-sensitive views.</p></section>
<section><h2>17. Appendix</h2><h3>Top reusable declarations</h3>{{ top_table|safe }}
<h3>Extraction worker benchmark</h3>{{ benchmark_table|safe }}
<h3>Commands</h3><pre>just bootstrap
just probe
just golden
just inventory
just extract
just normalize
just validate
just analyze
just report</pre>
<p>Schema: <code>schemas/lean-graph-v1.md</code>. Compact artifacts adjacent to this
report contain fits, regressions, domain metrics, quality checks, and checksums.</p></section>
</main><footer>Deterministic report from compact artifacts. No CDN, remote JavaScript,
remote fonts, or external database.</footer></body></html>""")


CSS = """body{margin:0;background:#f2efe8;color:#17202a;font:16px/1.55 system-ui,sans-serif}
header,main,footer{max-width:1100px;margin:auto}header{padding:64px 28px 36px}
main{padding:0 28px}h1{font:700 clamp(2.4rem,7vw,5.4rem)/.95 Georgia,serif;
max-width:900px;margin:.2em 0}h2{font:700 2rem Georgia,serif;border-top:1px solid #bbb;
padding-top:32px}section{padding:12px 0 28px}.eyebrow{letter-spacing:.18em;font-weight:700}
.status{padding:14px 18px;border-left:6px solid #27824b;background:#e5f4e9}
.status.bad{border-color:#b83232;background:#fae5e5}svg,img{max-width:100%;height:auto;
background:#fbfaf7;margin:12px 0}table{border-collapse:collapse;width:100%;font-size:.86rem;
display:block;overflow:auto}th,td{border-bottom:1px solid #ccc;text-align:left;padding:7px 9px;
white-space:nowrap}th{background:#ded9ce}code,pre{background:#e7e3da;padding:.15em .35em}
pre{padding:16px;overflow:auto}.caption{color:#505962}.figure{margin:18px 0}
footer{padding:42px 28px 70px;color:#59636e}"""


def generate(run_kind: str) -> dict[str, Any]:
    metrics = ROOT / "results" / "metrics"
    tables = ROOT / "results" / "tables"
    report = ROOT / "results" / "report"
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
            json.loads((ROOT / "results" / "extraction-benchmark.json").read_text())["rows"]
        )
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
            nodes["source_bytes"].fill_null(0).to_list(),
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
            nodes["value_expr_nodes"].fill_null(0).to_list(),
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
            domains["alpha"].fill_null(0).to_list(),
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
            f'n={summary["declaration_count"]} declarations unless noted.</figcaption></figure>'
        )
        for name in figures
    }
    inline = {
        name: (
            f'<figure class="figure">{svg}<figcaption>'
            f'n={summary["declaration_count"]} declarations unless noted.</figcaption></figure>'
        )
        for name, svg in figures.items()
    }
    context = {
        "css": CSS,
        "quality": quality,
        "summary": summary,
        "manifest": manifest,
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
        "regressions_table": render_table(regressions, 10),
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
    (ROOT / "results" / f"report-{run_kind}-summary.json").write_text(
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
