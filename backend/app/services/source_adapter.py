from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import httpx

from app.config import Settings
from app.models import SourceConnection, SnapshotMeta, WeeklyPestelState

SAMPLE_DIR = Path(__file__).resolve().parents[1] / "samples"
ARCHIVE_RUN_PATH = Path(__file__).resolve().parents[1] / "archive" / "latest_run.json"


class SourceAdapter:
    def __init__(self, settings: Settings):
        self.settings = settings

    async def connection(self) -> SourceConnection:
        snapshots = await self.list_snapshots()
        mode = "external" if self.settings.has_external_source else "archive" if self._has_archive() else "sample"
        return SourceConnection(
            mode=mode,
            baseUrl=self.settings.source_base_url,
            manifestUrl=self.settings.source_snapshot_manifest_url,
            snapshotCount=len(snapshots),
            message=(
                "Using configured external snapshot source."
                if self.settings.has_external_source
                else "Using bundled 42-week Q-FIN archive."
                if mode == "archive"
                else "Using bundled sample snapshots because no archive or external source is configured."
            ),
        )

    async def list_snapshots(self) -> list[SnapshotMeta]:
        if self.settings.source_snapshot_manifest_url:
            manifest = await self._fetch_json(self.settings.source_snapshot_manifest_url)
            items = manifest.get("snapshots", manifest) if isinstance(manifest, dict) else manifest
            return [self._meta_from_manifest_item(item, index) for index, item in enumerate(items)]

        if self.settings.source_snapshot_urls:
            return [
                SnapshotMeta(
                    id=self._id_from_url(url, index),
                    label=self._label_from_url(url, index),
                    url=url,
                    source="external",
                )
                for index, url in enumerate(self.settings.source_snapshot_urls)
            ]

        if self._has_archive():
            return self._archive_manifest()

        return self._sample_manifest()

    async def get_snapshot(self, snapshot_id: str) -> tuple[SnapshotMeta, dict[str, Any]]:
        snapshots = await self.list_snapshots()
        matches = [item for item in snapshots if item.id == snapshot_id]
        if not matches:
            raise KeyError(f"Snapshot {snapshot_id} was not found")
        meta = matches[0]
        return meta, await self._load_by_meta(meta)

    async def get_snapshot_by_url(self, url: str, index: int = 0) -> tuple[SnapshotMeta, dict[str, Any]]:
        meta = SnapshotMeta(id=self._id_from_url(url, index), label=self._label_from_url(url, index), url=url, source="external")
        return meta, await self._load_by_meta(meta)

    async def _load_by_meta(self, meta: SnapshotMeta) -> dict[str, Any]:
        if meta.source == "archive":
            state = next(item for item in self._archive_series_raw() if item["weekId"] == meta.id)
            return self._snapshot_from_archive_state(state)
        if meta.source == "sample":
            manifest_item = next(item for item in self._sample_manifest_raw() if item["id"] == meta.id)
            return json.loads((SAMPLE_DIR / manifest_item["file"]).read_text(encoding="utf-8"))
        if not meta.url:
            raise ValueError(f"External snapshot {meta.id} has no URL")
        return await self._fetch_json(meta.url)

    async def _fetch_json(self, url: str) -> Any:
        resolved = urljoin(f"{self.settings.source_base_url.rstrip('/')}/", url) if self.settings.source_base_url and url.startswith("/") else url
        async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds, follow_redirects=True) as client:
            response = await client.get(resolved)
            response.raise_for_status()
            return response.json()

    def _meta_from_manifest_item(self, item: Any, index: int) -> SnapshotMeta:
        if isinstance(item, str):
            return SnapshotMeta(id=self._id_from_url(item, index), label=self._label_from_url(item, index), url=item, source="external")
        url = item.get("url") or item.get("path")
        if self.settings.source_base_url and url and url.startswith("/"):
            url = urljoin(f"{self.settings.source_base_url.rstrip('/')}/", url)
        return SnapshotMeta(
            id=str(item.get("id") or self._id_from_url(url or f"snapshot-{index}", index)),
            label=str(item.get("label") or item.get("name") or self._label_from_url(url or f"snapshot-{index}", index)),
            url=url,
            source="external",
        )

    def _sample_manifest(self) -> list[SnapshotMeta]:
        return [
            SnapshotMeta(id=item["id"], label=item["label"], url=None, source="sample")
            for item in self._sample_manifest_raw()
        ]

    def _sample_manifest_raw(self) -> list[dict[str, str]]:
        return json.loads((SAMPLE_DIR / "snapshots.json").read_text(encoding="utf-8"))

    def _has_archive(self) -> bool:
        return ARCHIVE_RUN_PATH.exists()

    def _archive_payload(self) -> dict[str, Any]:
        return json.loads(ARCHIVE_RUN_PATH.read_text(encoding="utf-8"))

    def _archive_series_raw(self) -> list[dict[str, Any]]:
        return self._archive_payload().get("weeklyPestelSeries") or []

    def _archive_manifest(self) -> list[SnapshotMeta]:
        return [
            SnapshotMeta(
                id=str(item["weekId"]),
                label=str(item.get("label") or item["weekId"]),
                url=None,
                source="archive",
            )
            for item in self._archive_series_raw()
        ]

    def archive_series(self, snapshot_ids: list[str] | None = None) -> list[WeeklyPestelState]:
        states = self._archive_series_raw()
        requested = set(snapshot_ids or [])
        selected = [item for item in states if not requested or item.get("weekId") in requested]
        if requested and len(selected) != len(requested):
            found = {item.get("weekId") for item in selected}
            missing = sorted(requested - found)
            raise KeyError(f"Snapshot {', '.join(missing)} was not found")
        return [WeeklyPestelState.model_validate({**item, "source": "archive"}) for item in selected]

    def should_use_archive_series(self, snapshot_ids: list[str], snapshot_urls: list[str]) -> bool:
        if snapshot_urls or self.settings.has_external_source or not self._has_archive():
            return False
        archive_ids = {item["weekId"] for item in self._archive_series_raw()}
        return not snapshot_ids or set(snapshot_ids).issubset(archive_ids)

    def _snapshot_from_archive_state(self, state: dict[str, Any]) -> dict[str, Any]:
        graph = state.get("graph") or {}
        sample_clusters = graph.get("sampleClusters") or []
        return {
            "id": state.get("weekId"),
            "label": state.get("label"),
            "precomputedPestel": state.get("pestel"),
            "levels": {
                "L2": {
                    "clusterSizes": [cluster.get("clusterSize") or 1 for cluster in sample_clusters],
                    "graph": {
                        "nodes": [
                            {"id": cluster.get("id", index), "text": cluster.get("text", "")}
                            for index, cluster in enumerate(sample_clusters)
                        ],
                        "edges": graph.get("rawEdges") or [],
                    },
                }
            },
        }

    def _id_from_url(self, url: str, index: int) -> str:
        clean = url.rstrip("/").split("/")[-1].replace(".json", "")
        return clean or f"snapshot-{index + 1}"

    def _label_from_url(self, url: str, index: int) -> str:
        return self._id_from_url(url, index).replace("_", " ").replace("-", " ").title()
