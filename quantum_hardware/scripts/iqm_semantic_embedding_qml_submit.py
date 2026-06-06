from __future__ import annotations

import argparse
import json
import math
import os
import random
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from common import circuit_fingerprint, circuit_to_qasm, job_id_from, load_payload, safe_backend_name, write_json
from iqm_qiskit_submit import DEFAULT_IQM_QUANTUM_COMPUTER, DEFAULT_IQM_SERVER_URL, import_iqm_provider


CLASS_NAMES = ["stable", "event_aligned", "event_divergent", "uncertain"]
CLASS_BITS = ["00", "01", "10", "11"]


def normalize_distribution(values: list[float]) -> list[float]:
    total = sum(max(0.0, value) for value in values)
    if total <= 0:
        return [1.0 / len(values) for _ in values]
    return [max(0.0, value) / total for value in values]


def unit(vector: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(vector))
    if norm <= 0:
        return vector.astype(float)
    return vector.astype(float) / norm


def cosine(left: np.ndarray, right: np.ndarray) -> float:
    return float(np.dot(unit(left), unit(right)))


def read_embeddings(path: str | Path) -> dict[str, Any]:
    data = load_payload(path)
    if data.get("schema") != "quantumfinances.semantic_embeddings.v1":
        raise SystemExit("Embedding file must use schema quantumfinances.semantic_embeddings.v1.")
    weeks = data.get("weeks") or []
    if len(weeks) < 2:
        raise SystemExit("Semantic QML needs at least two weekly embedding vectors.")
    event = (data.get("event") or {}).get("embedding")
    if not isinstance(event, list) or not event:
        raise SystemExit("Embedding file has no event.embedding vector.")
    dimensions = {len(event)}
    for week in weeks:
        embedding = week.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise SystemExit(f"Week {week.get('weekId')} has no embedding vector.")
        dimensions.add(len(embedding))
    if len(dimensions) != 1:
        raise SystemExit(f"Embedding dimensions are inconsistent: {sorted(dimensions)}")
    return data


def as_matrix(embeddings: dict[str, Any]) -> tuple[list[str], np.ndarray, np.ndarray]:
    weeks = embeddings.get("weeks") or []
    week_ids = [str(week.get("weekId") or f"W{index}") for index, week in enumerate(weeks)]
    week_vectors = np.asarray([week["embedding"] for week in weeks], dtype=float)
    event_vector = np.asarray((embeddings.get("event") or {})["embedding"], dtype=float)
    return week_ids, week_vectors, event_vector


def deterministic_extra_components(dimension: int, rows: int, seed_material: str) -> np.ndarray:
    seed = int.from_bytes(seed_material.encode("utf-8")[:8].ljust(8, b"0"), "little", signed=False)
    rng = np.random.default_rng(seed)
    matrix = rng.choice([-1.0, 1.0], size=(rows, dimension))
    matrix /= math.sqrt(max(1, dimension))
    return matrix


def fit_projection(vectors: np.ndarray, latent_dim: int, seed_material: str) -> dict[str, Any]:
    if latent_dim < 2:
        raise SystemExit("latent-dim must be at least 2 because the circuit measures two scenario bits.")
    mean = vectors.mean(axis=0)
    centered = vectors - mean
    if centered.shape[0] >= 2 and np.any(np.abs(centered) > 1e-12):
        _u, _s, vt = np.linalg.svd(centered, full_matrices=False)
        components = vt[: min(latent_dim, vt.shape[0])]
    else:
        components = np.empty((0, vectors.shape[1]))
    if components.shape[0] < latent_dim:
        extra = deterministic_extra_components(
            vectors.shape[1],
            latent_dim - components.shape[0],
            seed_material=f"{seed_material}:{latent_dim}:{vectors.shape[1]}",
        )
        components = np.vstack([components, extra])
    raw = centered @ components.T
    scale = float(np.percentile(np.abs(raw), 95)) if raw.size else 1.0
    if scale <= 1e-9:
        scale = 1.0
    return {
        "mean": mean,
        "components": components,
        "scale": scale,
    }


def project(vector: np.ndarray, projection: dict[str, Any]) -> list[float]:
    raw = (vector - projection["mean"]) @ projection["components"].T
    scaled = 0.5 + 0.46 * np.tanh(raw / projection["scale"])
    return [float(max(0.0, min(1.0, value))) for value in scaled]


def semantic_target(current: np.ndarray, next_vector: np.ndarray, event: np.ndarray) -> list[float]:
    current_similarity = (cosine(current, event) + 1.0) / 2.0
    next_similarity = (cosine(next_vector, event) + 1.0) / 2.0
    delta = next_similarity - current_similarity
    drift = 1.0 - ((cosine(current, next_vector) + 1.0) / 2.0)
    stable = max(0.0, 1.0 - 3.0 * abs(delta) - 1.2 * drift)
    event_aligned = max(0.0, 0.15 + 2.8 * max(0.0, delta) + 0.45 * next_similarity)
    event_divergent = max(0.0, 0.15 + 2.8 * max(0.0, -delta) + 0.45 * (1.0 - next_similarity))
    uncertain = max(0.0, 0.12 + 1.8 * drift)
    return normalize_distribution([stable, event_aligned, event_divergent, uncertain])


def build_semantic_circuit(features: list[float], theta: list[float], layers: int, measure: bool = True):
    from qiskit import QuantumCircuit

    qubits = len(features)
    circuit = QuantumCircuit(qubits, 2 if measure else 0, name="quantumfinances_semantic_embedding_qml")
    for qubit, feature in enumerate(features):
        circuit.ry((feature - 0.5) * math.pi, qubit)
        circuit.rz((feature - 0.5) * math.pi / 2.0, qubit)

    cursor = 0
    for _layer in range(layers):
        for qubit in range(qubits):
            circuit.ry(theta[cursor], qubit)
            cursor += 1
        for qubit in range(qubits):
            circuit.cx(qubit, (qubit + 1) % qubits)
        for qubit in range(qubits):
            circuit.rz(theta[cursor], qubit)
            cursor += 1

    circuit.barrier()
    if measure:
        circuit.measure([0, 1], [0, 1])
    return circuit


def exact_probabilities(features: list[float], theta: list[float], layers: int) -> list[float]:
    from qiskit.quantum_info import Statevector

    state = Statevector.from_instruction(build_semantic_circuit(features, theta, layers=layers, measure=False))
    raw = state.probabilities_dict()
    probabilities = [0.0, 0.0, 0.0, 0.0]
    for bitstring, probability in raw.items():
        measured = bitstring[-2:][::-1]
        probabilities[int(measured, 2)] += float(probability)
    return normalize_distribution(probabilities)


def cross_entropy(predicted: list[float], target: list[float]) -> float:
    return -sum(target[index] * math.log(max(1e-9, predicted[index])) for index in range(4))


def train_theta(
    samples: list[tuple[list[float], list[float]]],
    seed: int,
    iterations: int,
    layers: int,
    latent_dim: int,
) -> tuple[list[float], list[dict[str, float]]]:
    rng = random.Random(seed)
    theta = [rng.uniform(-0.25, 0.25) for _ in range(layers * latent_dim * 2)]

    def loss(values: list[float]) -> float:
        return sum(cross_entropy(exact_probabilities(features, values, layers=layers), target) for features, target in samples) / max(
            1, len(samples)
        )

    current = loss(theta)
    history = [{"iteration": 0, "loss": current}]
    scale = 0.35
    for iteration in range(1, iterations + 1):
        candidate = [value + rng.gauss(0.0, scale) for value in theta]
        candidate_loss = loss(candidate)
        if candidate_loss < current:
            theta = candidate
            current = candidate_loss
        scale *= 0.97
        if iteration == iterations or iteration % 10 == 0:
            history.append({"iteration": iteration, "loss": current})
    return theta, history


def build_training_set(
    payload: dict[str, Any],
    embeddings: dict[str, Any],
    latent_dim: int,
) -> tuple[list[tuple[list[float], list[float]]], list[float], dict[str, Any]]:
    week_ids, week_vectors, event = as_matrix(embeddings)
    projection = fit_projection(
        np.vstack([week_vectors, event.reshape(1, -1)]),
        latent_dim=latent_dim,
        seed_material=str(embeddings.get("embeddingModel") or "semantic_embedding_qml"),
    )
    samples: list[tuple[list[float], list[float]]] = []
    for index in range(len(week_vectors) - 1):
        features = project(week_vectors[index], projection)
        target = semantic_target(week_vectors[index], week_vectors[index + 1], event)
        samples.append((features, target))
    latest_features = project(week_vectors[-1], projection)
    latest_event_similarity = (cosine(week_vectors[-1], event) + 1.0) / 2.0
    metadata = {
        "qmlType": "semantic_embedding_temporal_variational_classifier",
        "embeddingProvider": embeddings.get("embeddingProvider"),
        "embeddingModel": embeddings.get("embeddingModel"),
        "embeddingDimension": int(embeddings.get("embeddingDimension") or len(event)),
        "latentDim": latent_dim,
        "projection": {
            "method": "pca_plus_seeded_signed_random_projection",
            "scale": projection["scale"],
            "componentRows": int(projection["components"].shape[0]),
        },
        "weekIds": week_ids,
        "trainingSampleCount": len(samples),
        "inputRunId": payload.get("runId"),
        "sourcePayloadRunId": embeddings.get("sourcePayloadRunId"),
        "latestLatentFeatures": latest_features,
        "latestEventCosineSimilarity01": latest_event_similarity,
        "classNames": dict(zip(CLASS_BITS, CLASS_NAMES, strict=True)),
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
    parser = argparse.ArgumentParser(description="Train and submit a semantic-embedding temporal QML circuit to IQM.")
    parser.add_argument("--input", default=str(Path(__file__).resolve().parents[1] / "inputs" / "latest_run.json"))
    parser.add_argument(
        "--embeddings",
        default=str(Path(__file__).resolve().parents[1] / "inputs" / "latest_run.embeddings.json"),
    )
    parser.add_argument("--out", default="")
    parser.add_argument("--shots", type=int, default=512)
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--iterations", type=int, default=120)
    parser.add_argument("--latent-dim", type=int, default=8)
    parser.add_argument("--layers", type=int, default=2)
    parser.add_argument("--max-statevector-qubits", type=int, default=12)
    parser.add_argument("--server-url", default=os.getenv("IQM_SERVER_URL", DEFAULT_IQM_SERVER_URL))
    parser.add_argument("--quantum-computer", default=os.getenv("IQM_QUANTUM_COMPUTER", DEFAULT_IQM_QUANTUM_COMPUTER))
    parser.add_argument("--backend", default=os.getenv("IQM_BACKEND", ""))
    parser.add_argument("--token", default="", help="Optional explicit token. Prefer IQM_TOKEN env var.")
    parser.add_argument("--optimization-level", type=int, default=1, choices=[0, 1, 2, 3])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--submit", action="store_true")
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()

    if args.latent_dim > args.max_statevector_qubits:
        raise SystemExit(
            f"Training uses exact statevector loss and is capped at {args.max_statevector_qubits} qubits. "
            "Use more batch jobs/shots now, or add a separate HPC optimizer before increasing latent-dim."
        )

    payload = load_payload(args.input)
    embeddings = read_embeddings(args.embeddings)
    samples, latest_features, qml_metadata = build_training_set(payload, embeddings, latent_dim=args.latent_dim)
    theta, training_history = train_theta(
        samples,
        seed=args.seed,
        iterations=args.iterations,
        layers=args.layers,
        latent_dim=args.latent_dim,
    )
    inference_probabilities = exact_probabilities(latest_features, theta, layers=args.layers)
    circuit = build_semantic_circuit(latest_features, theta, layers=args.layers, measure=True)
    qasm = circuit_to_qasm(circuit)
    fingerprint = circuit_fingerprint(qasm)
    output_path = (
        Path(args.out)
        if args.out
        else Path(__file__).resolve().parents[1] / "receipts" / f"iqm_semantic_qml_{fingerprint}.json"
    )

    receipt: dict[str, Any] = {
        "provider": "iqm",
        "mode": "dry_run" if not args.submit else "submitted",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "inputPath": str(Path(args.input).resolve()),
        "embeddingPath": str(Path(args.embeddings).resolve()),
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
            "layers": args.layers,
            "trainingHistory": training_history,
            "learnedTheta": theta,
            "inferenceProbabilities": dict(zip(CLASS_NAMES, inference_probabilities, strict=True)),
        },
        "qasm": qasm,
    }

    if not args.submit:
        write_json(output_path, receipt)
        print(f"IQM semantic embedding QML dry-run receipt written: {output_path}")
        print("Add --submit to run the trained semantic QML inference circuit on IQM hardware.")
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
    print(f"IQM semantic embedding QML receipt written: {output_path}")
    print(f"Job id: {receipt.get('jobId')}")
    if "counts" in receipt:
        print(f"Counts: {json.dumps(receipt['counts'], sort_keys=True)}")


if __name__ == "__main__":
    main()
