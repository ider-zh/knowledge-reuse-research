set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

doctor:
    uv run python -m knowledge_reuse.sources.lean_mathlib.commands.doctor

bootstrap:
    uv sync --frozen
    uv run python -m knowledge_reuse.sources.lean_mathlib.commands.bootstrap

probe:
    uv run python -m knowledge_reuse.sources.lean_mathlib.commands.run_probe

golden:
    uv run python -m knowledge_reuse.sources.lean_mathlib.commands.run_golden
    uv run pytest -q tests/sources/lean_mathlib/golden

inventory:
    uv run python -m knowledge_reuse.sources.lean_mathlib.commands.inventory
    uv run python -m knowledge_reuse.sources.lean_mathlib.commands.make_shards

extract-smoke:
    uv run python -m knowledge_reuse.sources.lean_mathlib.commands.run_extract --smoke

extract:
    uv run python -m knowledge_reuse.sources.lean_mathlib.commands.run_extract

benchmark-extract:
    uv run python -m knowledge_reuse.sources.lean_mathlib.commands.benchmark_extract

normalize:
    uv run python -m knowledge_reuse.sources.lean_mathlib.normalize

normalize-smoke:
    uv run python -m knowledge_reuse.sources.lean_mathlib.normalize --smoke

validate:
    uv run python -m knowledge_reuse.sources.lean_mathlib.commands.verify_run

validate-smoke:
    uv run python -m knowledge_reuse.sources.lean_mathlib.commands.verify_run --smoke

analyze:
    uv run python -m knowledge_reuse.sources.lean_mathlib.metrics

analyze-smoke:
    uv run python -m knowledge_reuse.sources.lean_mathlib.metrics --smoke

report-smoke:
    uv run python -m knowledge_reuse.sources.lean_mathlib.report --smoke

report:
    uv run python -m knowledge_reuse.sources.lean_mathlib.report

all: bootstrap probe golden inventory extract normalize validate analyze report
