from pipeline.domains import domain_from_module, module_from_path
from scripts.inventory import exclusion_for


def test_module_and_domain_mapping() -> None:
    path = __import__("pathlib").Path("Mathlib/NumberTheory/Basic.lean")
    module = module_from_path(path)
    assert module == "Mathlib.NumberTheory.Basic"
    assert domain_from_module(module) == "NumberTheory"


def test_exclusion_matches_root_and_mathlib_relative_paths() -> None:
    rules = [{"pattern": "Counterexamples/**", "reason": "not primary"}]
    assert exclusion_for("Mathlib/Counterexamples/X.lean", rules) == rules[0]
