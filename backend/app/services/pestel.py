from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from app.models import PestelVector, WeeklyPestelState

PESTEL_DIMENSIONS: dict[str, list[str]] = {
    "political": [
        "government",
        "policy",
        "election",
        "minister",
        "parliament",
        "geopolitical",
        "war",
        "conflict",
        "sanction",
        "defense",
        "defence",
        "nato",
        "russia",
        "ukraine",
    ],
    "economic": [
        "market",
        "economy",
        "finance",
        "inflation",
        "trade",
        "tariff",
        "stock",
        "labor",
        "business",
        "price",
        "bank",
        "growth",
        "investment",
    ],
    "social": [
        "family",
        "health",
        "education",
        "community",
        "migration",
        "culture",
        "students",
        "children",
        "strike",
        "protest",
        "employment",
        "housing",
    ],
    "technological": [
        "technology",
        "ai",
        "data",
        "digital",
        "software",
        "robot",
        "cyber",
        "innovation",
        "semiconductor",
        "cloud",
        "platform",
        "crypto",
        "blockchain",
    ],
    "environmental": [
        "climate",
        "energy",
        "nature",
        "environment",
        "sustainability",
        "weather",
        "emissions",
        "mineral",
        "oil",
        "gas",
        "electricity",
        "storm",
    ],
    "legal": [
        "law",
        "court",
        "crime",
        "legal",
        "regulation",
        "rights",
        "police",
        "trial",
        "ban",
        "compliance",
        "lawsuit",
    ],
}

RISK_TERMS = {
    "attack",
    "war",
    "conflict",
    "crisis",
    "sanction",
    "tariff",
    "inflation",
    "recession",
    "crime",
    "trial",
    "lawsuit",
    "ban",
    "strike",
    "protest",
    "shortage",
    "decline",
    "risk",
    "uncertainty",
}


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def strip_html(value: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", str(value))
    return re.sub(r"\s+", " ", no_tags).strip()


def tokens(text: str) -> list[str]:
    return [part.lower() for part in re.split(r"[^A-Za-z0-9]+", text) if part]


def graph_degree_map(edges: list[Any]) -> dict[int, int]:
    degree: dict[int, int] = {}
    for edge in edges:
        if not isinstance(edge, (list, tuple)) or len(edge) < 2:
            continue
        left, right = int(edge[0]), int(edge[1])
        degree[left] = degree.get(left, 0) + 1
        degree[right] = degree.get(right, 0) + 1
    return degree


def extract_weekly_pestel(snapshot_id: str, label: str, snapshot: dict[str, Any], source: str) -> WeeklyPestelState:
    level = snapshot.get("levels", {}).get("L2")
    if not level:
        raise ValueError("Snapshot is missing levels.L2 graph data")

    graph = level.get("graph") or {"nodes": [], "edges": []}
    nodes = graph.get("nodes") or []
    edges = graph.get("edges") or []
    cluster_sizes = level.get("clusterSizes") or []
    degree = graph_degree_map(edges)
    max_degree = max([1, *degree.values()])
    max_size = max([1, *[float(size or 0) for size in cluster_sizes]])

    weighted_scores = {key: 0.0 for key in PESTEL_DIMENSIONS}
    total_weight = 0.0
    sample_clusters: list[dict[str, Any]] = []

    for index, node in enumerate(nodes):
        node_id = int(node.get("id", index))
        text = strip_html(node.get("text", ""))
        if len(sample_clusters) < 12:
            sample_clusters.append(
                {
                    "id": node_id,
                    "clusterSize": cluster_sizes[node_id] if node_id < len(cluster_sizes) else None,
                    "text": text[:320],
                }
            )
        token_counts = Counter(tokens(text))
        cluster_size = float(cluster_sizes[node_id] if node_id < len(cluster_sizes) else cluster_sizes[index] if index < len(cluster_sizes) else 1)
        volume = clamp(math.log1p(cluster_size) / math.log1p(max_size))
        centrality = clamp(degree.get(node_id, 0) / max_degree)
        risk_hits = sum(token_counts[term] for term in RISK_TERMS)
        severity = clamp(math.tanh(risk_hits / 4) * 0.75 + min(len(text) / 2500, 0.25))
        confidence = clamp(0.3 + volume * 0.25 + centrality * 0.2 + severity * 0.15)
        weight = 0.25 + volume * 0.25 + centrality * 0.25 + confidence * 0.25
        total_weight += weight

        for key, keywords in PESTEL_DIMENSIONS.items():
            hits = sum(token_counts[word] for word in keywords)
            score = clamp(math.tanh(hits / 4) * 0.55 + volume * 0.15 + centrality * 0.1 + severity * 0.1 + confidence * 0.1)
            weighted_scores[key] += score * weight

    if total_weight == 0:
        total_weight = 1.0

    pestel = PestelVector(**{key: clamp(value / total_weight) for key, value in weighted_scores.items()})
    return WeeklyPestelState(
        weekId=snapshot_id,
        label=label,
        pestel=pestel,
        graph={"nodes": len(nodes), "edges": len(edges), "rawEdges": edges[:24], "sampleClusters": sample_clusters},
        clusterCount=len(nodes),
        edgeCount=len(edges),
        source=source,  # type: ignore[arg-type]
    )


def pestel_to_vector(pestel: PestelVector) -> list[float]:
    return [
        pestel.political,
        pestel.economic,
        pestel.social,
        pestel.technological,
        pestel.environmental,
        pestel.legal,
    ]
