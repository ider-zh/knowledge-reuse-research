import inspect

import knowledge_reuse.sources.lean_mathlib.report
from knowledge_reuse.sources.lean_mathlib.report import TITLES, line_svg, points_svg


def test_report_contract_has_all_sections_and_figures() -> None:
    source = inspect.getsource(knowledge_reuse.sources.lean_mathlib.report)
    for section in range(1, 18):
        assert f"<h2>{section}." in source
    assert len(TITLES) >= 13
    assert 'src="http' not in source
    assert "唯一 DAG 节点 U" in source
    assert "Value 可观测性按声明类型分布" in source
    assert "Token 代理量" in source
    assert "getDeclarationValue?" in source
    assert "饱和截断" not in source
    assert "缓存不等于截断" not in source
    assert '.fill_null(0)' not in source
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
    ):
        assert explanation in source
    assert "教学例子，不是实验数据" in source


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
