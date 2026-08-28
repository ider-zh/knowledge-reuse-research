from knowledge_reuse.sources.lean_mathlib.commands.doctor import main


def test_doctor_has_required_tools() -> None:
    assert main() == 0
