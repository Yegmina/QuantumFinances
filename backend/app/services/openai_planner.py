from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from app.config import Settings
from app.models import (
    DimensionWeights,
    EngineDecision,
    EventProbability,
    ForecastScenario,
    PestelVector,
    RunRequest,
    ScenarioSimilarity,
    WeeklyPestelState,
)
from app.services.forecast import PESTEL_KEYS
from app.services.pestel import clamp


PESTEL_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {key: {"type": "number"} for key in PESTEL_KEYS},
    "required": PESTEL_KEYS,
}

SCENARIO_SIMILARITY_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "scenarioId": {"type": "string"},
        "scenarioProbability": {"type": "number"},
        "similarity": {"type": "number"},
        "weightedContribution": {"type": "number"},
        "dimensionScores": PESTEL_SCHEMA,
    },
    "required": ["scenarioId", "scenarioProbability", "similarity", "weightedContribution", "dimensionScores"],
}

SCENARIO_PLAN_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "rationale": {"type": "string"},
        "confidence": {"type": "number"},
        "scenarioCount": {"type": "integer"},
        "shots": {"type": "integer"},
        "seed": {"type": "integer"},
        "dimensionWeights": PESTEL_SCHEMA,
        "eventVector": PESTEL_SCHEMA,
        "calibratedWeeks": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "weekId": {"type": "string"},
                    "pestel": PESTEL_SCHEMA,
                },
                "required": ["weekId", "pestel"],
            },
        },
        "forecastScenarios": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "label": {"type": "string"},
                    "probability": {"type": "number"},
                    "pestel": PESTEL_SCHEMA,
                    "explanation": {"type": "string"},
                },
                "required": ["id", "label", "probability", "pestel", "explanation"],
            },
        },
        "eventProbability": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "eventText": {"type": "string"},
                "eventVector": PESTEL_SCHEMA,
                "probability": {"type": "number"},
                "vectorFit": {"type": "number"},
                "plausibilityFactor": {"type": "number"},
                "calibrationLabel": {"type": "string"},
                "explanation": {"type": "string"},
                "dimensionWeights": PESTEL_SCHEMA,
                "scenarioSimilarities": {
                    "type": "array",
                    "items": SCENARIO_SIMILARITY_SCHEMA,
                },
            },
            "required": [
                "eventText",
                "eventVector",
                "probability",
                "vectorFit",
                "plausibilityFactor",
                "calibrationLabel",
                "explanation",
                "dimensionWeights",
                "scenarioSimilarities",
            ],
        },
    },
    "required": [
        "rationale",
        "confidence",
        "scenarioCount",
        "shots",
        "seed",
        "dimensionWeights",
        "eventVector",
        "calibratedWeeks",
        "forecastScenarios",
        "eventProbability",
    ],
}


class CalibratedWeekPlan(BaseModel):
    weekId: str
    pestel: PestelVector


class OpenAiScenarioPlan(BaseModel):
    rationale: str
    confidence: float
    scenarioCount: int
    shots: int
    seed: int
    dimensionWeights: DimensionWeights
    eventVector: PestelVector
    calibratedWeeks: list[CalibratedWeekPlan]
    forecastScenarios: list[ForecastScenario]
    eventProbability: EventProbability


def _compact_week(state: WeeklyPestelState) -> dict[str, Any]:
    return {
        "weekId": state.weekId,
        "label": state.label,
        "pestelBaseline": state.pestel.model_dump(),
        "clusterCount": state.clusterCount,
        "edgeCount": state.edgeCount,
        "graph": state.graph,
    }


def _extract_output_text(response: dict[str, Any]) -> str:
    if isinstance(response.get("output_text"), str):
        return response["output_text"]

    for output in response.get("output", []):
        for content in output.get("content", []):
            text = content.get("text")
            if isinstance(text, str):
                return text

    raise ValueError("OpenAI response did not include output text")


def _clamped_pestel(values: PestelVector) -> PestelVector:
    return PestelVector(**{key: clamp(value) for key, value in values.model_dump().items()})


def _rounded_shots(value: int) -> int:
    bounded = int(clamp(value, 128, 8192))
    return max(128, min(8192, round(bounded / 128) * 128))


def _normalized_scenarios(scenarios: list[ForecastScenario], requested_count: int) -> list[ForecastScenario]:
    trimmed = scenarios[: max(2, min(8, requested_count or len(scenarios)))]
    if len(trimmed) < 2:
        raise ValueError("OpenAI returned fewer than two forecast scenarios")

    total = sum(max(0.0, scenario.probability) for scenario in trimmed) or 1.0
    normalized: list[ForecastScenario] = []
    for index, scenario in enumerate(trimmed):
        normalized.append(
            ForecastScenario(
                id=scenario.id or f"future-{index + 1}",
                label=scenario.label,
                probability=clamp(max(0.0, scenario.probability) / total),
                pestel=_clamped_pestel(scenario.pestel),
                explanation=scenario.explanation,
            )
        )
    return normalized


def _normalized_event_probability(
    event_probability: EventProbability,
    event_text: str,
    event_vector: PestelVector,
    weights: DimensionWeights,
    scenarios: list[ForecastScenario],
) -> EventProbability:
    scenario_map = {scenario.id: scenario for scenario in scenarios}
    similarities: list[ScenarioSimilarity] = []
    for item in event_probability.scenarioSimilarities:
        scenario = scenario_map.get(item.scenarioId)
        similarities.append(
            ScenarioSimilarity(
                scenarioId=item.scenarioId,
                scenarioProbability=scenario.probability if scenario else clamp(item.scenarioProbability),
                similarity=clamp(item.similarity),
                weightedContribution=clamp(item.weightedContribution),
                dimensionScores={key: clamp(value) for key, value in item.dimensionScores.items()},
            )
        )

    if not similarities:
        similarities = [
            ScenarioSimilarity(
                scenarioId=scenario.id,
                scenarioProbability=scenario.probability,
                similarity=0,
                weightedContribution=0,
                dimensionScores={key: 0 for key in PESTEL_KEYS},
            )
            for scenario in scenarios
        ]

    return EventProbability(
        eventText=event_text,
        eventVector=_clamped_pestel(event_vector),
        probability=clamp(event_probability.probability),
        vectorFit=clamp(event_probability.vectorFit),
        plausibilityFactor=clamp(event_probability.plausibilityFactor),
        calibrationLabel=event_probability.calibrationLabel,
        explanation=event_probability.explanation,
        dimensionWeights=weights,
        scenarioSimilarities=similarities,
    )


def apply_calibrated_weeks(series: list[WeeklyPestelState], plan: OpenAiScenarioPlan) -> list[WeeklyPestelState]:
    calibrated = {week.weekId: week for week in plan.calibratedWeeks}
    refined: list[WeeklyPestelState] = []
    for state in series:
        week = calibrated.get(state.weekId)
        if not week:
            refined.append(state)
            continue
        refined.append(state.model_copy(update={"pestel": _clamped_pestel(week.pestel)}))
    return refined


def deterministic_decision(payload: RunRequest) -> EngineDecision:
    return EngineDecision(
        source="local_baseline",
        model="QuantumFinances temporal vector engine",
        rationale="QuantumFinances used the weekly PESTEL trajectory, graph intensity, event text, and weighted vector similarity to complete this scenario path.",
        confidence=0.5,
        scenarioCount=payload.scenarioCount,
        shots=payload.shots,
        seed=payload.seed,
        dimensionWeights=payload.dimensionWeights,
        eventVector=PestelVector(
            political=0.2,
            economic=0.7,
            social=0.15,
            technological=0.45,
            environmental=0.1,
            legal=0.25,
        ),
    )


async def generate_openai_plan(
    settings: Settings,
    payload: RunRequest,
    series: list[WeeklyPestelState],
) -> tuple[EngineDecision, list[WeeklyPestelState], list[ForecastScenario], EventProbability]:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY is required for OpenAI scenario planning")

    requested_count = max(2, min(8, payload.scenarioCount))
    input_payload = {
        "eventText": payload.eventText,
        "requestedScenarioCount": requested_count,
        "requestedShots": payload.shots,
        "requestedSeed": payload.seed,
        "currentDimensionWeights": payload.dimensionWeights.model_dump(),
        "weeklySourcePestelSeries": [_compact_week(state) for state in series],
    }
    system_prompt = (
        "You are the QuantumFinances scenario engine. Decide the PESTEL weights, event vector, "
        "weekly PESTEL calibration, next-week future scenarios, scenario probabilities, "
        "event probability, quantum shot count, and seed from the provided source graph summaries. "
        "Return calibratedWeeks for every input week, but include only weekId and pestel; do not include "
        "per-week reasoning. Keep all rationale and explanations concise. "
        "Return calibrated numeric values in 0..1 for PESTEL dimensions. "
        "Return scenario probabilities that sum to 1. Use the requested scenario count unless the "
        "data strongly suggests a nearby count between 2 and 8. Keep shots between 512 and 4096 "
        "for a hardware-ready hackathon run. Estimate eventProbability.probability directly as "
        "your calibrated probability that the user's event happens in the stated time horizon. "
        "Do not use semantic vector fit alone as the final probability. Use common-sense base rates, "
        "event severity, time horizon, weekly PESTEL state, scenario branches, and uncertainty. "
        "Set vectorFit to the weighted event-to-scenario vector match, plausibilityFactor to your "
        "judged event plausibility multiplier, and explain the calibration in plain language. "
        "Avoid wording that frames the output as mock, "
        "unsupported, or fake; use run, scenario engine, quantum receipt, or circuit execution. "
        "Do not include markdown."
    )

    request_body = {
        "model": settings.openai_model,
        "input": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps(input_payload, ensure_ascii=False)},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "quantumfinances_scenario_plan",
                "strict": True,
                "schema": SCENARIO_PLAN_SCHEMA,
            }
        },
        "reasoning": {"effort": "low"},
        "max_output_tokens": 16000,
    }

    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        response = await client.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {settings.openai_api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
        )
        response.raise_for_status()
        raw = response.json()

    try:
        plan = OpenAiScenarioPlan.model_validate_json(_extract_output_text(raw))
    except (ValidationError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"OpenAI returned an invalid QuantumFinances plan: {exc}") from exc

    scenarios = _normalized_scenarios(plan.forecastScenarios, plan.scenarioCount)
    calibrated_series = apply_calibrated_weeks(series, plan)
    decision = EngineDecision(
        source="ai",
        model=settings.openai_model,
        rationale=plan.rationale,
        confidence=clamp(plan.confidence),
        scenarioCount=len(scenarios),
        shots=_rounded_shots(plan.shots),
        seed=plan.seed,
        dimensionWeights=plan.dimensionWeights,
        eventVector=_clamped_pestel(plan.eventVector),
    )
    event_probability = _normalized_event_probability(
        plan.eventProbability,
        payload.eventText,
        decision.eventVector,
        decision.dimensionWeights,
        scenarios,
    )
    return decision, calibrated_series, scenarios, event_probability
