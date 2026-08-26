import inspect

import pipeline.report
from pipeline.report import TITLES


def test_report_contract_has_all_sections_and_figures() -> None:
    source = inspect.getsource(pipeline.report)
    for section in range(1, 18):
        assert f"<h2>{section}." in source
    assert len(TITLES) >= 13
    assert 'src="http' not in source
