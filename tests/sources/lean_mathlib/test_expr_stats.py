import pathlib
import shutil
import subprocess


ROOT = pathlib.Path(__file__).resolve().parents[3]
LAKE = shutil.which("lake") or str(pathlib.Path.home() / ".elan" / "bin" / "lake")


def test_shared_dag_tree_count_is_exact_beyond_uint64() -> None:
    subprocess.run(
        [LAKE, "build", "lean-graph-expr-stats-test"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run(
        [LAKE, "env", ".lake/build/bin/lean-graph-expr-stats-test"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert result.stdout.strip() == "exact_tree_occurrences=2417851639229258349412351"
