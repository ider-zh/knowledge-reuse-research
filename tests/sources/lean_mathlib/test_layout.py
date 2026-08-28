from knowledge_reuse.sources.lean_mathlib.layout import (
    CONFIG_PATH,
    DATA_ROOT,
    RESULTS_ROOT,
    ROOT,
    run_results_root,
)


def test_lean_paths_are_source_and_experiment_namespaced() -> None:
    assert CONFIG_PATH == (
        ROOT / "experiments" / "lean_mathlib_v1" / "config" / "experiment-v1.toml"
    )
    assert DATA_ROOT == ROOT / "data" / "lean_mathlib"
    assert RESULTS_ROOT == ROOT / "results" / "lean_mathlib_v1"


def test_smoke_and_full_results_are_isolated() -> None:
    smoke = run_results_root("smoke")
    full = run_results_root("full")
    assert smoke != full
    assert smoke == RESULTS_ROOT / "runs" / "smoke"
    assert full == RESULTS_ROOT / "runs" / "full"
