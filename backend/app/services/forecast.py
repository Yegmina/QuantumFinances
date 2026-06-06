from __future__ import annotations

import math
import random

from app.models import ForecastScenario, PestelVector, WeeklyPestelState
from app.services.pestel import clamp

PESTEL_KEYS = ["political", "economic", "social", "technological", "environmental", "legal"]


def _as_dict(state: WeeklyPestelState) -> dict[str, float]:
    return state.pestel.model_dump()


def _scenario_label(index: int) -> str:
    labels = ["Trend continuation", "Risk acceleration", "Mean reversion", "Volatility branch", "Policy shock", "Technology shock", "Legal shock", "Mixed uncertainty"]
    return labels[index] if index < len(labels) else f"Scenario {index + 1}"


def forecast_scenarios(series: list[WeeklyPestelState], scenario_count: int, seed: int) -> list[ForecastScenario]:
    if not series:
        raise ValueError("At least one weekly PESTEL state is required")

    rng = random.Random(seed)
    latest = _as_dict(series[-1])
    previous = _as_dict(series[-2]) if len(series) > 1 else latest
    first = _as_dict(series[0])
    horizon = max(1, len(series) - 1)
    trend = {key: (latest[key] - first[key]) / horizon for key in PESTEL_KEYS}
    residual = {key: abs(latest[key] - previous[key]) for key in PESTEL_KEYS}

    raw_scenarios: list[tuple[float, ForecastScenario]] = []
    for index in range(scenario_count):
        branch_strength = (index - (scenario_count - 1) / 2) / max(1, scenario_count - 1)
        values: dict[str, float] = {}
        distance = 0.0

        for key in PESTEL_KEYS:
            persistence = latest[key] * 0.62
            trend_component = (latest[key] + trend[key]) * 0.28
            mean_component = ((latest[key] + previous[key]) / 2) * 0.1
            noise = (rng.random() - 0.5) * (0.08 + residual[key] * 0.35)
            shock = branch_strength * (0.06 + residual[key] * 0.2)
            value = clamp(persistence + trend_component + mean_component + noise + shock)
            values[key] = value
            distance += abs(value - latest[key])

        weight = math.exp(-distance * 2.2) * (1.0 + 0.1 * (scenario_count - index))
        raw_scenarios.append(
            (
                weight,
                ForecastScenario(
                    id=f"future-{index + 1}",
                    label=_scenario_label(index),
                    probability=0,
                    pestel=PestelVector(**values),
                    explanation="Generated from latest-week persistence, historical trend, and residual uncertainty.",
                ),
            )
        )

    total = sum(weight for weight, _ in raw_scenarios) or 1
    return [scenario.model_copy(update={"probability": weight / total}) for weight, scenario in raw_scenarios]

