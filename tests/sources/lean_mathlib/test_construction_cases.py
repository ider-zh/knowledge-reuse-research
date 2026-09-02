from knowledge_reuse.sources.lean_mathlib.construction_cases import source_excerpt


def test_source_excerpt_is_pinned_and_line_addressable() -> None:
    observed = source_excerpt("Mathlib/Data/Seq/Computation.lean", 99, 103)

    assert observed["start_line"] == 99
    assert observed["end_line"] == 103
    assert "unsafe def run" in observed["code"]
    assert "run ca" in observed["code"]
    assert observed["source_url"].endswith(
        "/Mathlib/Data/Seq/Computation.lean#L99-L103"
    )
