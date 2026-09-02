import inspect

import knowledge_reuse.sources.lean_mathlib.report
import polars as pl
from knowledge_reuse.sources.lean_mathlib.report import (
    TITLES,
    build_audit_status,
    line_svg,
    points_svg,
    scaled_powerlaw_ccdf,
    select_heatmap_domains,
)


def test_report_contract_has_all_sections_and_figures() -> None:
    source = inspect.getsource(knowledge_reuse.sources.lean_mathlib.report)
    for section in range(1, 18):
        assert f"<h2>{section}." in source
    assert len(TITLES) == 15
    assert list(TITLES.values()) == [
        f"图 {number} · {title.split(' · ', 1)[1]}"
        for number, title in enumerate(TITLES.values(), 1)
    ]
    assert 'src="http' not in source
    assert "唯一 DAG 节点 U" in source
    assert "Value 可观测性按声明类型分布" in source
    assert "Token 代理量" in source
    assert "getDeclarationValue?" in source
    assert "饱和截断" not in source
    assert "缓存不等于截断" not in source
    assert ".fill_null(0)" not in source
    assert "report-claims-v1" in source
    assert "report-examples-v1" in source
    assert "从真实边到完整图" in source
    for explanation in (
        "精化（elaboration）",
        "有向图",
        "CCDF（互补累积分布）",
        "Gini 系数",
        "重尾（heavy tail）",
        "Spearman ρ 怎样读",
        "为什么用负二项 GLM",
        "95% CI（置信区间）",
        "H*ref 怎样计算",
        "稳健性检查",
        "与 Veldhuizen 2005 的正面对照",
        "degree_tail_alpha",
        "beta_rank",
        "instance 当前必须报告为 not available",
        "五个可检验命题的明确结论",
    ):
        assert explanation in source
    assert "教学例子，不是实验数据" in source
    assert "H*ref(d)=-Σ p_d(b) log p_d(b) / log(D)" in source
    assert "当前不可检验" in source
    assert source.index("先解释本页第一次出现的名词") < source.index("一句话结论")
    assert "Lean 官方语言参考：Definitions" in source
    assert "β=1 才是恰好 1/r" in source
    assert "0–1 集中度" in source
    assert "provenance 审计不完整" not in source
    assert "completeness.configured_corpus" not in source
    assert "个模块全部成功提取" not in source
    assert "图不是由 import 关系生成" in source
    assert "没有把源码或 pretty-printed Expr 当成文本搜索" in source
    assert ".const targetName universes" in source
    assert "每个唯一 <code>(src,dst,edge_type)</code> 保存一行" in source
    assert "完整语义图保留 <code>A→A</code>" in source


def test_points_svg_skips_missing_metrics() -> None:
    rendered = points_svg("test", [None, 4.0], [2.0, 3.0], "x", "y")
    assert rendered.count("<circle ") == 1


def test_points_svg_sampling_is_independent_of_input_order() -> None:
    x_values = list(range(1, 4_001))
    y_values = [value % 97 + 1 for value in x_values]
    forward = points_svg("test", x_values, y_values, "x", "y")
    backward = points_svg("test", x_values[::-1], y_values[::-1], "x", "y")
    assert forward == backward


def test_line_svg_downsamples_display_without_changing_analysis() -> None:
    values = list(range(1, 10_001))
    rendered = line_svg("test", [("all", values, values)], "x", "y")
    polyline = rendered.split('<polyline points="', 1)[1].split('"', 1)[0]
    assert len(polyline.split()) <= 700


def test_powerlaw_overlay_starts_at_empirical_tail_mass() -> None:
    values = scaled_powerlaw_ccdf([10.0, 20.0], 10.0, 2.0, 0.2)
    assert values == [0.2, 0.1]


def test_heatmap_selects_most_connected_domains_not_alphabetical_prefix() -> None:
    frame = pl.DataFrame(
        {
            "src_domain": ["A", "Topology", "NumberTheory", "A"],
            "dst_domain": ["B", "A", "Topology", "B"],
            "dependency_pair_count": [1, 100, 80, 1],
            "row_share": [0.5, 1.0, 1.0, 0.5],
        }
    )
    assert select_heatmap_domains(frame, 3) == ["Topology", "A", "NumberTheory"]


def test_audit_distinguishes_graph_completeness_from_legacy_provenance() -> None:
    audit = build_audit_status(
        {"passed": True, "extraction_completeness": 1},
        {"passed": True, "checks": {"api": True}},
        {"passed": True, "checks": {"fixture": True}},
        {"extractor_revision_status": "not_recorded_in_legacy_raw_manifest"},
    )
    assert audit["graph_complete"] is True
    assert audit["provenance_complete"] is False
    assert audit["overall_status"] == "graph_complete_provenance_incomplete"
