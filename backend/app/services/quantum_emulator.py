from __future__ import annotations

import hashlib
import math
import random

from app.models import ForecastScenario, QuantumRunReceipt, WeeklyPestelState
from app.services.pestel import pestel_to_vector


def _derive_pairs(series: list[WeeklyPestelState], qubits: int = 6) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for state in series[-3:]:
        for edge in state.graph.get("rawEdges", []):
            if not isinstance(edge, (list, tuple)) or len(edge) < 2:
                continue
            pair = (abs(int(edge[0])) % qubits, abs(int(edge[1])) % qubits)
            if pair[0] == pair[1] or pair in seen or (pair[1], pair[0]) in seen:
                continue
            seen.add(pair)
            pairs.append(pair)
            if len(pairs) >= 8:
                return pairs
    return pairs or [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5)]


def _qasm(features: list[float], pairs: list[tuple[int, int]]) -> str:
    lines = [
        "OPENQASM 3.0;",
        "include \"stdgates.inc\";",
        "qubit[6] q;",
        "bit[2] c;",
    ]
    for index, value in enumerate(features):
        angle = value * math.pi - math.pi / 2
        lines.append(f"ry({angle:.6f}) q[{index}];")
    for control, target in pairs:
        lines.append(f"cx q[{control}], q[{target}];")
    for index in range(6):
        lines.append(f"ry({0.13 * (index + 1):.6f}) q[{index}];")
    lines.append("c[0] = measure q[0];")
    lines.append("c[1] = measure q[1];")
    return "\n".join(lines)


def create_quantum_receipt(series: list[WeeklyPestelState], scenarios: list[ForecastScenario], shots: int, seed: int) -> QuantumRunReceipt:
    latest_features = pestel_to_vector(series[-1].pestel)
    pairs = _derive_pairs(series)
    qasm = _qasm(latest_features, pairs)
    digest = hashlib.sha256(f"{latest_features}-{pairs}-{seed}".encode("utf-8")).hexdigest()[:12]
    rng = random.Random(seed + int(digest[:4], 16))

    buckets = {"00": 0.0, "01": 0.0, "10": 0.0, "11": 0.0}
    names = list(buckets)
    for index, scenario in enumerate(scenarios):
        target = names[index % len(names)]
        buckets[target] += scenario.probability * (0.85 + rng.random() * 0.3)

    total = sum(buckets.values()) or 1.0
    probabilities = {key: value / total for key, value in buckets.items()}
    counts = {key: round(value * shots) for key, value in probabilities.items()}
    counts["00"] += shots - sum(counts.values())

    return QuantumRunReceipt(
        executionMode="circuit_receipt",
        targetProvider="ibm_runtime_sampler_v2_later",
        hardwareJobSubmitted=False,
        localRunId=f"qrun-{digest}",
        circuitQasm=qasm,
        qubits=6,
        depth=6 + len(pairs) + 6 + 2,
        shots=shots,
        counts=counts,
        probabilities=probabilities,
    )
