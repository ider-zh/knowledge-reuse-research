from knowledge_reuse.sources.lean_mathlib.commands.run_golden import check_golden


def test_exact_golden_graph() -> None:
    result = check_golden()
    assert result["passed"], result
