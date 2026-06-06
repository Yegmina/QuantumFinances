from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

PESTEL_KEYS = ["political", "economic", "social", "technological", "environmental", "legal"]


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def load_payload(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_json(path: str | Path, data: dict[str, Any]) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    return output_path


def latest_pestel_vector(payload: dict[str, Any]) -> list[float]:
    series = payload.get("weeklyPestelSeries") or []
    if not series:
        raise ValueError("Payload has no weeklyPestelSeries")
    pestel = series[-1].get("pestel") or {}
    return [clamp(float(pestel.get(key, 0.0))) for key in PESTEL_KEYS]


def scenario_probabilities(payload: dict[str, Any]) -> list[float]:
    scenarios = payload.get("forecastScenarios") or []
    values = [max(0.0, float(item.get("probability", 0.0))) for item in scenarios]
    total = sum(values)
    if not values or total <= 0:
        return [0.25, 0.25, 0.25, 0.25]
    return [value / total for value in values]


def derive_entanglement_pairs(payload: dict[str, Any], qubits: int = 6, limit: int = 4) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for state in (payload.get("weeklyPestelSeries") or [])[-3:]:
        raw_edges = ((state.get("graph") or {}).get("rawEdges") or [])
        for edge in raw_edges:
            if not isinstance(edge, (list, tuple)) or len(edge) < 2:
                continue
            left = abs(int(edge[0])) % qubits
            right = abs(int(edge[1])) % qubits
            pair = (left, right)
            reverse = (right, left)
            if left == right or pair in seen or reverse in seen:
                continue
            seen.add(pair)
            pairs.append(pair)
            if len(pairs) >= limit:
                return pairs
    return pairs or [(0, 1), (1, 2), (2, 3)]


def build_quantumfinances_circuit(
    payload: dict[str, Any],
    measured_qubits: int = 2,
    entanglement_limit: int = 4,
    measure_all: bool = False,
):
    try:
        from qiskit import QuantumCircuit
    except ImportError as exc:
        raise RuntimeError(
            "Qiskit is required. Install the provider requirements from quantum_hardware first."
        ) from exc

    features = latest_pestel_vector(payload)
    pairs = derive_entanglement_pairs(payload, qubits=len(features), limit=entanglement_limit)
    scenario_probs = scenario_probabilities(payload)

    classical_bits = len(features) if measure_all else max(1, min(measured_qubits, len(features)))
    circuit = QuantumCircuit(len(features), classical_bits, name="quantumfinances_pestel")

    for index, value in enumerate(features):
        circuit.ry(value * math.pi - math.pi / 2, index)

    for control, target in pairs:
        circuit.cx(control, target)

    for index, probability in enumerate(scenario_probs[: len(features)]):
        circuit.rz((probability - 0.25) * math.pi, index)
        circuit.ry(probability * math.pi / 2, index)

    circuit.barrier()
    if measure_all:
        circuit.measure(range(len(features)), range(len(features)))
    else:
        circuit.measure(range(classical_bits), range(classical_bits))

    metadata = {
        "pestelKeys": PESTEL_KEYS,
        "latestPestelVector": features,
        "entanglementPairs": pairs,
        "scenarioProbabilities": scenario_probs,
        "measuredQubits": classical_bits,
        "measureAll": measure_all,
    }
    return circuit, metadata


def circuit_to_qasm(circuit: Any) -> str:
    try:
        from qiskit import qasm3

        return qasm3.dumps(circuit)
    except Exception:
        if hasattr(circuit, "qasm"):
            return circuit.qasm()
        return str(circuit)


def circuit_fingerprint(qasm: str) -> str:
    return hashlib.sha256(qasm.encode("utf-8")).hexdigest()[:16]


def job_id_from(job: Any) -> str | None:
    value = getattr(job, "job_id", None)
    if callable(value):
        return str(value())
    if value is not None:
        return str(value)
    value = getattr(job, "id", None)
    if callable(value):
        return str(value())
    return str(value) if value is not None else None


def counts_from_ibm_sampler_result(result: Any) -> dict[str, int]:
    pub_result = result[0] if hasattr(result, "__getitem__") else result
    data = getattr(pub_result, "data", None)
    if data is None:
        return {}

    candidates = []
    for name in ("c", "meas", "cr"):
        if hasattr(data, name):
            candidates.append(getattr(data, name))
    for name in dir(data):
        if name.startswith("_"):
            continue
        try:
            value = getattr(data, name)
        except Exception:
            continue
        if value not in candidates:
            candidates.append(value)

    for candidate in candidates:
        get_counts = getattr(candidate, "get_counts", None)
        if callable(get_counts):
            counts = get_counts()
            return {str(key): int(value) for key, value in counts.items()}
    return {}


def safe_backend_name(backend: Any) -> str | None:
    name = getattr(backend, "name", None)
    if callable(name):
        return str(name())
    return str(name) if name is not None else None
