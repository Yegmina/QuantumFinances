from __future__ import annotations

from app.models import RunResponse

_RUNS: dict[str, RunResponse] = {}


def save_run(result: RunResponse) -> None:
    _RUNS[result.runId] = result


def get_run(run_id: str) -> RunResponse | None:
    return _RUNS.get(run_id)
