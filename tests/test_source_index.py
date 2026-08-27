from knowledge_reuse.sources.lean_mathlib.source_index import slice_range


def test_slice_range_uses_lean_line_and_column_coordinates(tmp_path) -> None:
    source = tmp_path / "Fixture.lean"
    source.write_text("ignore\ntheorem t : True := by\n  trivial\nignore\n")
    assert slice_range(source, 2, 0, 3, 9) == "theorem t : True := by\n  trivial"
