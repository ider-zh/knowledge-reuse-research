from scripts.doctor import main


def test_doctor_has_required_tools() -> None:
    assert main() == 0

