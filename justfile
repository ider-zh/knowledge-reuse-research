set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

doctor:
    uv run python scripts/doctor.py

bootstrap:
    uv sync --frozen
    uv run python scripts/bootstrap.py

probe:
    uv run python scripts/run_probe.py

golden:
    uv run python scripts/run_golden.py
    uv run pytest -q tests/golden

inventory:
    uv run python -m scripts.inventory

extract-smoke:
    uv run python -m scripts.run_extract --smoke

extract:
    uv run python -m scripts.run_extract

benchmark-extract:
    uv run python -m scripts.benchmark_extract

normalize:
    uv run python -m pipeline.normalize

normalize-smoke:
    uv run python -m pipeline.normalize --smoke

validate:
    uv run python -m scripts.verify_run

validate-smoke:
    uv run python -m scripts.verify_run --smoke

analyze:
    uv run python -m pipeline.metrics

analyze-smoke:
    uv run python -m pipeline.metrics --smoke

report-smoke:
    uv run python -m pipeline.report --smoke

report:
    uv run python -m pipeline.report

all: bootstrap probe golden inventory extract normalize validate analyze report
