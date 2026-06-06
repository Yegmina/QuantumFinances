from __future__ import annotations

import argparse
import json
import math
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import PESTEL_KEYS, circuit_fingerprint, circuit_to_qasm, job_id_from, load_payload, safe_backend_name, write_json
from iqm_qiskit_submit import DEFAULT_IQM_QUANTUM_COMPUTER, DEFAULT_IQM_SERVER_URL, import_iqm_provider


LATENT_KEYS = ["policy_legal", "economic_tech", "social_environment", "temporal_graph"]


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def normalize(values: list[float]) -> list[float]:
    total = sum(max(0.0, value) for value in values)
    if total <= 0:
        return [1.0 / len(values) for _ in values]
    return [max(0.0, value) / total for value in values]


def pestel_vector(item: dict[str, Any]) -> list[float]:
    pestel = item.get("pestel") or {}
    return [clamp(float(pestel.get(key, 0.0))) for key in PESTEL_KEYS]


def event_vector(payload: dict[str, Any]) -> list[float]:
    raw = ((payload.get("eventProbability") or {}).get("eventVector") or (payload.get("engineDecision") or {}).get("eventVector") or {})
    return [clamp(float(raw.get(key, 0.0))) for key in PESTEL_KEYS]


def dimension_weights(payload: dict[str, Any]) -> list[float]:
    raw = ((payload.get("eventProbability") or {}).get("dimensionWeights") or (payload.get("engineDecision") or {}).get("dimensionWeights") or {})
    values = [max(0.0, float(raw.get(key, 1.0 / len(PESTEL_KEYS)))) for key in PESTEL_KEYS]
    return normalize(values)


def graph_intensity(item: dict[str, Any]) -> float:
    graph = item.get("graph") or {}
    nodes = max(1.0, float(graph.get("nodes") or item.get("clusterCount") or 1))
    edges = float(graph.get("edges") or item.get("edgeCount") or 0)
    return clamp(edges / (nodes * max(1.0, nodes - 1.0)))


def latent_features(pestel: list[float], event: list[float], weights: list[float], graph_value: float, previous: list[float] | None) -> list[float]:
    weighted = [clamp(0.62 * pestel[i] + 0.38 * event[i]) * (0.55 + weights[i]) for i in range(len(PESTEL_KEYS))]
    trend = 0.0 if previous is None else sum(pestel[i] - previous[i] for i in range(len(PESTEL_KEYS))) / len(PESTEL_KEYS)
    return [
        clamp((weighted[0] + weighted[5]) / 2.0),
        clamp((weighted[1] + weighted[3]) / 2.0),
        clamp((weighted[2] + weighted[4]) / 2.0),
        clamp(0.50 + 0.75 * trend + 0.35 * graph_value),
    ]


def scenario_target(next_pestel: list[float], current_pestel: list[float], event: list[float], weights: list[float]) -> list[float]:
    weighted_alignment = sum(weights[i] * (1.0 - abs(next_pestel[i] - event[i])) for i in range(len(PESTEL_KEYS)))
    weighted_trend = sum(weights[i] * (next_pestel[i] - current_pestel[i]) for i in range(len(PESTEL_KEYS)))
    volatility = sum(abs(next_pestel[i] - current_pestel[i]) for i in range(len(PESTEL_KEYS))) / len(PESTEL_KEYS)
    stable = clamp(1.0 - 2.8 * volatility)
    aligned_up = clamp(weighted_alignment * (0.55 + max(0.0, weighted_trend) * 4.0))
    aligned_down = clamp((1.0 - weighted_alignment) * (0.45 + max(0.0, -weighted_trend) * 4.0))
    uncertain = clamp(0.15 + volatility * 1.8)
    return normalize([stable, aligned_up, aligned_down, uncertain])


def scenario_target_from_forecasts(payload: dict[str, Any], latest: list[float], event: list[float], weights: list[float]) -> list[float]:
    scenarios = payload.get("forecastScenarios") or []
    if not scenarios:
        return scenario_target(latest, latest, event, weights)
    mixed = [0.0, 0.0, 0.0, 0.0]
    for scenario in scenarios:
        future = [clamp(float((scenario.get("pestel") or {}).get(key, 0.0))) for key in PESTEL_KEYS]
        probability = max(0.0, float(scenario.get("probability", 0.0)))
        target = scenario_target(future, latest, event, weights)
        for index, value in enumerate(target):
            mixed[index] += probability * value
    return normalize(mixed)


def build_qml_circuit(features: list[float], theta: list[float], measure: bool = True):
    from qiskit import QuantumCircuit

    circuit = QuantumCircuit(4, 2 if measure else 0, name="quantumfinances_temporal_qml")
    for qubit, feature in enumerate(features):
        circuit.ry((feature - 0.5) * math.pi, qubit)
        circuit.rz((feature - 0.5) * math.pi / 2.0, qubit)

    cursor = 0
    for _layer in range(2):
        for qubit in range(4):
            circuit.ry(theta[cursor], qubit)
            cursor += 1
        circuit.cx(0, 1)
        circuit.cx(1, 2)
        circuit.cx(2, 3)
        circuit.cx(3, 0)
        for qubit in range(4):
            circuit.rz(theta[cursor], qubit)
            cursor += 1

    circuit.barrier()
    if measure:
        circuit.measure([0, 1], [0, 1])
    return circuit


def exact_probabilities(features: list[float], theta: list[float]) -> list[float]:
    from qiskit.quantum_info import Statevector

    state = Statevector.from_instruction(build_qml_circuit(features, theta, measure=False))
    raw = state.probabilities_dict()
    probs = [0.0, 0.0, 0.0, 0.0]
    for bitstring, probability in raw.items():
        measured = bitstring[-2:][::-1]
        probs[int(measured, 2)] += float(probability)
    return normalize(probs)


def cross_entropy(predicted: list[float], target: list[float]) -> float:
    return -sum(target[i] * math.log(max(1e-9, predicted[i])) for i in range(4))


def train_theta(samples: list[tuple[list[float], list[float]]], seed: int, iterations: int) -> tuple[list[float], list[dict[str, float]]]:
    rng = random.Random(seed)
    theta = [rng.uniform(-0.35, 0.35) for _ in range(16)]

    def loss(values: list[float]) -> float:
        return sum(cross_entropy(exact_probabilities(features, values), target) for features, target in samples) / max(1, len(samples))

    current = loss(theta)
    history = [{"iteration": 0, "loss": current}]
    scale = 0.45
    for iteration in range(1, iterations + 1):
        candidate = [value + rng.gauss(0.0, scale) for value in theta]
        candidate_loss = loss(candidate)
        if candidate_loss < current:
            theta = candidate
            current = candidate_loss
        scale *= 0.965
        if iteration == iterations or iteration % 10 == 0:
            history.append({"iteration": iteration, "loss": current})
    return theta, history


def build_training_set(payload: dict[str, Any]) -> tuple[list[tuple[list[float], list[float]]], list[float], dict[str, Any]]:
    series = payload.get("weeklyPestelSeries") or []
    if len(series) < 2:
        raise SystemExit("Temporal QML needs at least two weekly PESTEL vectors.")
    event = event_vector(payload)
    weights = dimension_weights(payload)
    vectors = [pestel_vector(item) for item in series]

    samples: list[tuple[list[float], list[float]]] = []
    previous: list[float] | None = None
    for index in range(len(series) - 1):
        features = latent_features(vectors[index], event, weights, graph_intensity(series[index]), previous)
        target = scenario_target(vectors[index + 1], vectors[index], event, weights)
        samples.append((features, target))
        previous = vectors[index]

    latest_features = latent_features(vectors[-1], event, weights, graph_intensity(series[-1]), vectors[-2] if len(vectors) > 1 else None)
    forecast_target = scenario_target_from_forecasts(payload, vectors[-1], event, weights)
    metadata = {
        "qmlType": "temporal_variational_quantum_classifier",
        "latentKeys": LATENT_KEYS,
        "pestelKeys": PESTEL_KEYS,
        "weekIds": [item.get("weekId") for item in series],
        "trainingSampleCount": len(samples),
        "eventText": ((payload.get("eventProbability") or {}).get("eventText") or payload.get("eventText")),
        "eventVector": dict(zip(PESTEL_KEYS, event, strict=True)),
        "dimensionWeights": dict(zip(PESTEL_KEYS, weights, strict=True)),
        "latestLatentFeatures": dict(zip(LATENT_KEYS, latest_features, strict=True)),
        "forecastTeacherDistribution": {
            "stable": forecast_target[0],
            "aligned_up": forecast_target[1],
            "aligned_down": forecast_target[2],
            "uncertain": forecast_target[3],
        },
    }
    return samples, latest_features, metadata


def result_counts(result: Any) -> dict[str, int]:
    get_counts = getattr(result, "get_counts", None)
    if callable(get_counts):
        return {str(key): int(value) for key, value in get_counts().items()}
    try:
        return {str(key): int(value) for key, value in result.results[0].data.counts.items()}
    except Exception:
        return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Train and submit a temporal PESTEL QML circuit to IQM Resonance.")
    parser.add_argument("--input", default=str(Path(__file__).resolve().parents[1] / "inputs" / "latest_run.json"))
    parser.add_argument("--out", default="")
    parser.add_argument("--shots", type=int, default=128)
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--iterations", type=int, default=60)
    parser.add_argument("--server-url", default=os.getenv("IQM_SERVER_URL", DEFAULT_IQM_SERVER_URL))
    parser.add_argument("--quantum-computer", default=os.getenv("IQM_QUANTUM_COMPUTER", DEFAULT_IQM_QUANTUM_COMPUTER))
    parser.add_argument("--backend", default=os.getenv("IQM_BACKEND", ""))
    parser.add_argument("--token", default="", help="Optional explicit token. Prefer IQM_TOKEN env var.")
    parser.add_argument("--optimization-level", type=int, default=1, choices=[0, 1, 2, 3])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()

    payload = load_payload(args.input)
    samples, latest_features, qml_metadata = build_training_set(payload)
    theta, training_history = train_theta(samples, seed=args.seed, iterations=args.iterations)
    inference_probabilities = exact_probabilities(latest_features, theta)
    circuit = build_qml_circuit(latest_features, theta, measure=True)
    qasm = circuit_to_qasm(circuit)
    fingerprint = circuit_fingerprint(qasm)
    output_path = Path(args.out) if args.out else Path(__file__).resolve().parents[1] / "receipts" / f"iqm_qml_{fingerprint}.json"

    receipt: dict[str, Any] = {
        "provider": "iqm",
        "mode": "dry_run" if not args.submit else "submitted",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "inputPath": str(Path(args.input).resolve()),
        "inputRunId": payload.get("runId"),
        "shots": args.shots,
        "hardwareJobSubmitted": False,
        "serverUrlConfigured": bool(args.server_url),
        "quantumComputerConfigured": bool(args.quantum_computer),
        "authConfigured": bool(args.token or os.getenv("IQM_TOKEN")),
        "circuitFingerprint": fingerprint,
        "circuitDepth": circuit.depth(),
        "qubits": circuit.num_qubits,
        "qml": {
            **qml_metadata,
            "trainingHistory": training_history,
            "learnedTheta": theta,
            "inferenceProbabilities": {
                "stable": inference_probabilities[0],
                "aligned_up": inference_probabilities[1],
                "aligned_down": inference_probabilities[2],
                "uncertain": inference_probabilities[3],
            },
        },
        "qasm": qasm,
    }

    if not args.submit:
        write_json(output_path, receipt)
        print(f"IQM temporal QML dry-run receipt written: {output_path}")
        print("Add --submit to run the trained QML inference circuit on IQM hardware.")
        return

    if not args.token and not os.getenv("IQM_TOKEN"):
        raise SystemExit("IQM_TOKEN is required for IQM Resonance submission.")

    from qiskit import transpile

    provider_kwargs = {}
    if args.quantum_computer:
        provider_kwargs["quantum_computer"] = args.quantum_computer
    if args.token:
        provider_kwargs["token"] = args.token
        os.environ.pop("IQM_TOKEN", None)
    provider = import_iqm_provider()(args.server_url, **provider_kwargs)
    backend = provider.get_backend(args.backend) if args.backend else provider.get_backend()
    transpiled = transpile(circuit, backend=backend, optimization_level=args.optimization_level)
    job = backend.run(transpiled, shots=args.shots)

    receipt.update(
        {
            "mode": "submitted",
            "hardwareJobSubmitted": True,
            "backend": safe_backend_name(backend),
            "jobId": job_id_from(job),
            "transpiledDepth": transpiled.depth(),
            "transpiledQasm": circuit_to_qasm(transpiled),
        }
    )

    if args.wait:
        result = job.result()
        receipt["counts"] = result_counts(result)
        receipt["resultRepr"] = repr(result)[:4000]

    write_json(output_path, receipt)
    print(f"IQM temporal QML receipt written: {output_path}")
    print(f"Job id: {receipt.get('jobId')}")
    if "counts" in receipt:
        print(f"Counts: {json.dumps(receipt['counts'], sort_keys=True)}")


if __name__ == "__main__":
    main()
