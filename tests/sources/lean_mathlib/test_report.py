import inspect

import knowledge_reuse.sources.lean_mathlib.report
from knowledge_reuse.sources.lean_mathlib.report import TITLES, line_svg, points_svg


def test_report_contract_has_all_sections_and_figures() -> None:
    source = inspect.getsource(knowledge_reuse.sources.lean_mathlib.report)
    for section in range(1, 18):
        assert f"<h2>{section}." in source
    assert len(TITLES) >= 13
    assert 'src="http' not in source
    assert "没有截断" in source
    assert "缓存不等于截断" in source
    assert '.fill_null(0)' not in source


def test_points_svg_skips_missing_metrics() -> None:
    rendered = points_svg("test", [None, 4.0], [2.0, 3.0], "x", "y")
    assert rendered.count("<circle ") == 1


def test_line_svg_downsamples_display_without_changing_analysis() -> None:
    values = list(range(1, 10_001))
    rendered = line_svg("test", [("all", values, values)], "x", "y")
    polyline = rendered.split('<polyline points="', 1)[1].split('"', 1)[0]
    assert len(polyline.split()) <= 700
