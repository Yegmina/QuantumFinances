from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import load_payload, write_json


DEFAULT_MODEL = "intfloat/multilingual-e5-large-instruct"


def l2_normalize(values: list[float]) -> list[float]:
    norm = sum(value * value for value in values) ** 0.5
    if norm <= 0:
        return values
    return [value / norm for value in values]


def weighted_average(vectors: list[list[float]], weights: list[float]) -> list[float]:
    if not vectors:
        raise ValueError("No vectors available for weighted average.")
    total = sum(max(0.0, weight) for weight in weights)
    if total <= 0:
        weights = [1.0 for _ in vectors]
        total = float(len(vectors))
    result = [0.0 for _ in vectors[0]]
    for vector, weight in zip(vectors, weights, strict=True):
        factor = max(0.0, weight) / total
        for index, value in enumerate(vector):
            result[index] += float(value) * factor
    return l2_normalize(result)


def cluster_texts(week: dict[str, Any]) -> list[dict[str, Any]]:
    clusters = ((week.get("graph") or {}).get("sampleClusters") or week.get("clusters") or [])
    records: list[dict[str, Any]] = []
    for cluster in clusters:
        text = str(cluster.get("text") or cluster.get("summary") or cluster.get("title") or "").strip()
        if not text:
            continue
        records.append(
            {
                "id": cluster.get("id"),
                "clusterSize": float(cluster.get("clusterSize") or cluster.get("size") or 1.0),
                "text": text,
            }
        )
    return records


def week_text(week: dict[str, Any]) -> str:
    clusters = cluster_texts(week)
    if clusters:
        return " ".join(item["text"] for item in clusters)
    return str(week.get("label") or week.get("weekId") or "").strip()


def event_text(payload: dict[str, Any]) -> str:
    return str(
        ((payload.get("eventProbability") or {}).get("eventText"))
        or ((payload.get("engineDecision") or {}).get("eventText"))
        or payload.get("eventText")
        or ""
    ).strip()


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def load_sentence_transformer(model_name: str, low_memory: bool):
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            "sentence-transformers is required for real local embeddings. "
            "Install quantum_hardware/requirements-embeddings.txt first."
        ) from exc
    model_kwargs = {"low_cpu_mem_usage": True} if low_memory else None
    if model_kwargs:
        return SentenceTransformer(model_name, model_kwargs=model_kwargs)
    return SentenceTransformer(model_name)


def encode_texts(model: Any, texts: list[str], batch_size: int, normalize: bool) -> list[list[float]]:
    encoded = model.encode(
        texts,
        batch_size=batch_size,
        normalize_embeddings=normalize,
        convert_to_numpy=True,
        show_progress_bar=True,
    )
    return [[float(value) for value in row] for row in encoded]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build non-OpenAI semantic embedding vectors from a QuantumFinances run payload."
    )
    parser.add_argument("--input", default=str(Path(__file__).resolve().parents[1] / "inputs" / "latest_run.json"))
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[1] / "inputs" / "latest_run.embeddings.json"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--include-clusters", action="store_true")
    parser.add_argument("--normalize", action="store_true", default=True)
    parser.add_argument("--low-memory", action="store_true", help="Load transformer weights with lower peak RAM usage.")
    args = parser.parse_args()

    payload = load_payload(args.input)
    series = payload.get("weeklyPestelSeries") or []
    if len(series) < 2:
        raise SystemExit("At least two weekly states are required to build temporal semantic embeddings.")

    event = event_text(payload)
    if not event:
        raise SystemExit("Payload has no event text to embed.")

    week_records = []
    all_texts = [event]
    for week in series:
        clusters = cluster_texts(week)
        combined = week_text(week)
        record = {
            "weekId": week.get("weekId"),
            "label": week.get("label"),
            "text": combined,
            "textHash": text_hash(combined),
            "clusters": clusters,
        }
        week_records.append(record)
        all_texts.extend(cluster["text"] for cluster in clusters)
        if not clusters:
            all_texts.append(combined)

    model = load_sentence_transformer(args.model, args.low_memory)
    vectors = encode_texts(model, all_texts, batch_size=args.batch_size, normalize=args.normalize)
    event_embedding = l2_normalize(vectors[0])

    cursor = 1
    weeks = []
    for record in week_records:
        clusters = record["clusters"]
        cluster_vectors: list[list[float]] = []
        for _cluster in clusters:
            cluster_vectors.append(l2_normalize(vectors[cursor]))
            cursor += 1
        if cluster_vectors:
            weights = [float(cluster["clusterSize"]) for cluster in clusters]
            week_embedding = weighted_average(cluster_vectors, weights)
        else:
            week_embedding = l2_normalize(vectors[cursor])
            cursor += 1

        output_week: dict[str, Any] = {
            "weekId": record["weekId"],
            "label": record["label"],
            "textHash": record["textHash"],
            "clusterCount": len(clusters),
            "embedding": week_embedding,
        }
        if args.include_clusters:
            output_week["clusters"] = [
                {
                    "id": cluster.get("id"),
                    "clusterSize": cluster.get("clusterSize"),
                    "textHash": text_hash(cluster["text"]),
                    "embedding": cluster_vector,
                }
                for cluster, cluster_vector in zip(clusters, cluster_vectors, strict=True)
            ]
        weeks.append(output_week)

    dimension = len(event_embedding)
    embedding_payload = {
        "schema": "quantumfinances.semantic_embeddings.v1",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "sourcePayloadRunId": payload.get("runId"),
        "sourceInputPath": str(Path(args.input).resolve()),
        "embeddingProvider": "local_sentence_transformer",
        "embeddingModel": args.model,
        "embeddingDimension": dimension,
        "normalized": args.normalize,
        "event": {
            "textHash": text_hash(event),
            "embedding": event_embedding,
        },
        "weeks": weeks,
    }
    write_json(args.out, embedding_payload)
    print(f"Semantic embedding payload written: {args.out}")
    print(f"Model: {args.model}")
    print(f"Dimension: {dimension}")
    print(f"Weeks: {len(weeks)}")


if __name__ == "__main__":
    main()
