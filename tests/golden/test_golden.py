from scripts.run_golden import check_golden


def test_exact_golden_graph() -> None:
    result = check_golden()
    assert result["passed"], result

