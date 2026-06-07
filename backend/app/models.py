from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


PestelKey = Literal["political", "economic", "social", "technological", "environmental", "legal"]


class SnapshotMeta(BaseModel):
    id: str
    label: str
    url: str | None = None
    source: Literal["external", "archive", "sample"] = "sample"


class SourceConnection(BaseModel):
    mode: Literal["external", "archive", "sample"]
    baseUrl: str | None = None
    manifestUrl: str | None = None
    snapshotCount: int
    message: str


class PestelVector(BaseModel):
    political: float = Field(ge=0, le=1)
    economic: float = Field(ge=0, le=1)
    social: float = Field(ge=0, le=1)
    technological: float = Field(ge=0, le=1)
    environmental: float = Field(ge=0, le=1)
    legal: float = Field(ge=0, le=1)


class WeeklyPestelState(BaseModel):
    weekId: str
    label: str
    pestel: PestelVector
    graph: dict[str, Any]
    clusterCount: int
    edgeCount: int
    source: Literal["external", "archive", "sample"]


class BuildSeriesRequest(BaseModel):
    snapshotIds: list[str] = Field(default_factory=list)
    snapshotUrls: list[str] = Field(default_factory=list)
    useOpenAi: bool = False


class BuildSeriesResponse(BaseModel):
    sourceConnection: SourceConnection
    weeklyPestelSeries: list[WeeklyPestelState]


class DimensionWeights(BaseModel):
    political: float = Field(default=0.2, ge=0, le=1)
    economic: float = Field(default=0.35, ge=0, le=1)
    social: float = Field(default=0.1, ge=0, le=1)
    technological: float = Field(default=0.2, ge=0, le=1)
    environmental: float = Field(default=0.05, ge=0, le=1)
    legal: float = Field(default=0.1, ge=0, le=1)


class RunRequest(BaseModel):
    snapshotIds: list[str] = Field(default_factory=list)
    snapshotUrls: list[str] = Field(default_factory=list)
    eventText: str = Field(default="Company becomes the biggest in its market")
    dimensionWeights: DimensionWeights = Field(default_factory=DimensionWeights)
    scenarioCount: int = Field(default=4, ge=2, le=8)
    shots: int = Field(default=2048, ge=128, le=8192)
    seed: int = 41
    useOpenAi: bool = True


class ForecastScenario(BaseModel):
    id: str
    label: str
    probability: float = Field(ge=0, le=1)
    pestel: PestelVector
    explanation: str


class ScenarioSimilarity(BaseModel):
    scenarioId: str
    scenarioProbability: float = Field(ge=0, le=1)
    similarity: float = Field(ge=0, le=1)
    weightedContribution: float = Field(ge=0, le=1)
    dimensionScores: dict[PestelKey, float]


class EventProbability(BaseModel):
    eventText: str
    eventVector: PestelVector
    probability: float = Field(ge=0, le=1)
    vectorFit: float = Field(ge=0, le=1)
    plausibilityFactor: float = Field(ge=0, le=1)
    calibrationLabel: str
    explanation: str
    dimensionWeights: DimensionWeights
    scenarioSimilarities: list[ScenarioSimilarity]


class EngineDecision(BaseModel):
    source: Literal["ai", "local_baseline"]
    model: str | None = None
    rationale: str
    confidence: float = Field(ge=0, le=1)
    scenarioCount: int = Field(ge=2, le=8)
    shots: int = Field(ge=128, le=8192)
    seed: int
    dimensionWeights: DimensionWeights
    eventVector: PestelVector


class QuantumRunReceipt(BaseModel):
    executionMode: Literal["circuit_receipt"]
    targetProvider: str
    hardwareJobSubmitted: bool
    localRunId: str
    circuitQasm: str
    qubits: int
    depth: int
    shots: int
    counts: dict[str, int]
    probabilities: dict[str, float]


class IntegrityNote(BaseModel):
    status: Literal["local_quantum_receipt", "hardware_verified"]
    message: str
    hardwareClaimAllowed: bool


class RunResponse(BaseModel):
    runId: str
    sourceConnection: SourceConnection
    engineDecision: EngineDecision
    weeklyPestelSeries: list[WeeklyPestelState]
    forecastScenarios: list[ForecastScenario]
    eventProbability: EventProbability
    quantumRun: QuantumRunReceipt
    integrity: IntegrityNote
