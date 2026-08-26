set shell := ["bash", "-eu", "-o", "pipefail", "-c"]

doctor:
    uv run python scripts/doctor.py

bootstrap:
    uv sync --frozen
    uv run python scripts/bootstrap.py

probe:
    uv run python scripts/run_probe.py

golden:
    uv run pytest -q tests/golden

inventory:
    uv run python scripts/inventory.py

extract-smoke:
    uv run python scripts/run_extract.py --smoke

extract:
    uv run python scripts/run_extract.py

normalize:
    uv run python -m pipeline.normalize

validate:
    uv run python scripts/verify_run.py

analyze:
    uv run python -m pipeline.metrics

report:
    uv run python -m pipeline.report

all: bootstrap probe golden inventory extract normalize validate analyze report

