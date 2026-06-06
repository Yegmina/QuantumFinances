from __future__ import annotations

import math
from collections import Counter

from app.models import DimensionWeights, EventProbability, ForecastScenario, PestelVector, ScenarioSimilarity
from app.services.forecast import PESTEL_KEYS
from app.services.pestel import PESTEL_DIMENSIONS, clamp, tokens


def event_text_to_pestel(event_text: str) -> PestelVector:
    token_counts = Counter(tokens(event_text))
    values = {}
    for key, keywords in PESTEL_DIMENSIONS.items():
        hits = sum(token_counts[word] for word in keywords)
        values[key] = clamp(0.12 + math.tanh(hits / 2) * 0.78)

    if max(values.values()) <= 0.12:
        values["economic"] = 0.7
        values["technological"] = 0.35
        values["legal"] = 0.25

    return PestelVector(**values)


def _weighted_cosine(event_values: dict[str, float], scenario_values: dict[str, float], weight_values: dict[str, float]) -> float:
    numerator = 0.0
    left_norm = 0.0
    right_norm = 0.0
    for key in PESTEL_KEYS:
        weight = weight_values[key]
        left = event_values[key]
        right = scenario_values[key]
        numerator += weight * left * right
        left_norm += weight * left * left
        right_norm += weight * right * right

    denominator = math.sqrt(left_norm) * math.sqrt(right_norm)
    if denominator == 0:
        return 0.0
    return clamp(numerator / denominator)


def score_event(
    event_text: str,
    scenarios: list[ForecastScenario],
    weights: DimensionWeights,
    event_vector: PestelVector | None = None,
) -> EventProbability:
    event_vector = event_vector or event_text_to_pestel(event_text)
    event_values = event_vector.model_dump()
    weight_values = weights.model_dump()

    similarities: list[ScenarioSimilarity] = []
    vector_fit = 0.0
    for scenario in scenarios:
        scenario_values = scenario.pestel.model_dump()
        dimension_scores = {key: clamp(1 - abs(event_values[key] - scenario_values[key])) for key in PESTEL_KEYS}
        weighted_similarity = _weighted_cosine(event_values, scenario_values, weight_values)
        contribution = scenario.probability * weighted_similarity
        vector_fit += contribution
        similarities.append(
            ScenarioSimilarity(
                scenarioId=scenario.id,
                scenarioProbability=scenario.probability,
                similarity=weighted_similarity,
                weightedContribution=contribution,
                dimensionScores=dimension_scores,
            )
        )

    return EventProbability(
        eventText=event_text,
        eventVector=event_vector,
        probability=clamp(vector_fit),
        vectorFit=clamp(vector_fit),
        plausibilityFactor=1.0,
        calibrationLabel="Vector baseline",
        explanation="Local vector baseline used when AI probability generation is disabled.",
        dimensionWeights=weights,
        scenarioSimilarities=similarities,
    )
