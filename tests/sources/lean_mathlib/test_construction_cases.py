import inspect

from knowledge_reuse.sources.lean_mathlib.construction_cases import (
    build_construction_cases,
    source_excerpt,
)


def test_source_excerpt_is_pinned_and_line_addressable() -> None:
    observed = source_excerpt("Mathlib/Data/Seq/Computation.lean", 99, 103)

    assert observed["start_line"] == 99
    assert observed["end_line"] == 103
    assert "unsafe def run" in observed["code"]
    assert "run ca" in observed["code"]
    assert observed["source_url"].endswith(
        "/Mathlib/Data/Seq/Computation.lean#L99-L103"
    )


def test_set_expr_interpretation_has_language_implementation_and_observation_evidence() -> None:
    source = inspect.getsource(build_construction_cases)
    assert "Lean Language Reference · Universes" in source
    assert "Lean/Parser/Term.lean#L134-L144" in source
    assert "Lean/Elab/BuiltinTerm.lean#L21-L34" in source
    assert "elabProp     → mkSort Level.zero" in source
    assert "raw ConstantInfo" in source
    assert "env.find? name → ConstantInfo" in source
    assert ".const targetName universes → count[targetName] += weight" in source
    assert "本抽取器不搜索源码字符串" in source
