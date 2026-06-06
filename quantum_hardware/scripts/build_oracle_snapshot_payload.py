from __future__ import annotations

import argparse
import asyncio
import gzip
import hashlib
import json
import os
import re
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings
from app.models import BuildSeriesResponse, IntegrityNote, RunRequest, RunResponse, SourceConnection
from app.services.event_scoring import score_event
from app.services.forecast import forecast_scenarios
from app.services.openai_planner import deterministic_decision, generate_openai_plan
from app.services.pestel import extract_weekly_pestel
from app.services.quantum_emulator import create_quantum_receipt


DATED_GRAPH_RE = re.compile(r"^graph_(\d{4}-\d{2}-\d{2})\.json$")
DATE_IN_PATH_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def fetch_json(url: str, token: str | None = None, timeout: int = 120) -> Any:
    headers = {"Accept": "application/json", "Accept-Encoding": "gzip, deflate"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url, headers=headers)
    with urlopen(request, timeout=timeout) as response:
        data = response.read()
        encoding = response.headers.get("Content-Encoding", "").lower()
        if encoding == "gzip":
            data = gzip.decompress(data)
        elif encoding == "deflate":
            data = zlib.decompress(data)
        return json.loads(data.decode("utf-8"))


def discover_dated_graphs(oracle_dir: Path) -> list[tuple[str, Path]]:
    discovered: list[tuple[str, Path]] = []
    for path in oracle_dir.glob("graph_*.json"):
        match = DATED_GRAPH_RE.match(path.name)
        if not match:
            continue
        discovered.append((match.group(1), path))
    discovered.sort(key=lambda item: item[0])
    if not discovered:
        raise SystemExit(f"No dated ORACLE graph snapshots found in {oracle_dir}")
    return discovered


def build_series(snapshot_paths: list[tuple[str, Path]]):
    series = []
    for snapshot_id, path in snapshot_paths:
        snapshot = load_json(path)
        series.append(
            extract_weekly_pestel(
                snapshot_id=snapshot_id,
                label=f"ORACLE {snapshot_id}",
                snapshot=snapshot,
                source="external",
            )
        )
    series.sort(key=lambda item: item.weekId)
    return series


def graph_items_from_manifest(manifest: Any, snapshot_kind: str) -> list[dict[str, Any]]:
    if isinstance(manifest, dict):
        items = manifest.get(snapshot_kind) or manifest.get("snapshots") or []
    else:
        items = manifest
    if not isinstance(items, list):
        raise SystemExit(f"Manifest did not contain a list for {snapshot_kind!r}.")
    return [item for item in items if isinstance(item, dict) and (item.get("value") or item.get("url") or item.get("path"))]


def id_from_manifest_item(item: dict[str, Any], index: int) -> str:
    raw = str(item.get("id") or item.get("value") or item.get("url") or item.get("path") or "")
    match = DATE_IN_PATH_RE.search(raw)
    if match:
        return match.group(1)
    return str(item.get("label") or f"snapshot-{index + 1}")


def log(message: str) -> None:
    print(message, flush=True)


def build_series_from_manifest_data(
    manifest: Any,
    source_label: str,
    base_url: str,
    snapshot_kind: str,
    token: str | None,
    snapshot_limit: int | None = None,
):
    items = graph_items_from_manifest(manifest, snapshot_kind)
    if not items:
        raise SystemExit(f"No {snapshot_kind} snapshots found in {source_label}")
    if snapshot_limit:
        items = items[:snapshot_limit]

    log(f"Loaded manifest entries: {len(items)} {snapshot_kind} snapshots from {source_label}")

    series = []
    for index, item in enumerate(items):
        snapshot_id = id_from_manifest_item(item, index)
        label = str(item.get("label") or f"ORACLE {snapshot_id}")
        if isinstance(item.get(snapshot_kind), dict):
            snapshot = item[snapshot_kind]
        else:
            raw_url = str(item.get("value") or item.get("url") or item.get("path"))
            snapshot_url = urljoin(f"{base_url.rstrip('/')}/", raw_url)
            log(f"[{index + 1}/{len(items)}] Fetching {snapshot_id}: {snapshot_url}")
            snapshot = fetch_json(snapshot_url, token=token)
        log(f"[{index + 1}/{len(items)}] Extracting PESTEL vector for {snapshot_id}")
        series.append(
            extract_weekly_pestel(
                snapshot_id=snapshot_id,
                label=label,
                snapshot=snapshot,
                source="external",
            )
        )
    series.sort(key=lambda item: item.weekId)
    log(f"Built weekly PESTEL series: {len(series)} weeks")
    return series, items


def build_series_from_manifest(manifest_url: str, base_url: str, snapshot_kind: str, token: str | None, snapshot_limit: int | None = None):
    log(f"Fetching manifest: {manifest_url}")
    manifest = fetch_json(manifest_url, token=token)
    return build_series_from_manifest_data(manifest, manifest_url, base_url, snapshot_kind, token, snapshot_limit)


def source_connection(snapshot_paths: list[tuple[str, Path]], oracle_dir: Path) -> SourceConnection:
    return SourceConnection(
        mode="external",
        baseUrl=None,
        manifestUrl=None,
        snapshotCount=len(snapshot_paths),
        message=(
            "Loaded the full locally available dated ORACLE graph snapshot set "
            f"from {oracle_dir}."
        ),
    )


def remote_source_connection(manifest_url: str | None, count: int) -> SourceConnection:
    return SourceConnection(
        mode="external",
        baseUrl="https://oraakkeli.metropolia.fi",
        manifestUrl=manifest_url,
        snapshotCount=count,
        message="Loaded ORACLE graph snapshots from the authenticated deployed ORACLE snapshot manifest.",
    )


def run_id_for(event_text: str, series: list[Any], quantum_run_id: str) -> str:
    material = {
        "eventText": event_text,
        "weeks": [state.weekId for state in series],
        "clusters": [state.clusterCount for state in series],
        "edges": [state.edgeCount for state in series],
        "quantumRunId": quantum_run_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    digest = hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()[:14]
    return f"run-{digest}"


async def create_run(args: argparse.Namespace) -> RunResponse:
    source = None
    if args.manifest_file:
        token = os.getenv(args.auth_token_env) if args.auth_token_env else None
        if args.require_auth and not token:
            raise SystemExit(f"{args.auth_token_env} is required to fetch snapshot files from {args.manifest_file}")
        manifest_path = Path(args.manifest_file)
        manifest = load_json(manifest_path)
        series, manifest_items = build_series_from_manifest_data(
            manifest=manifest,
            source_label=str(manifest_path),
            base_url=args.base_url,
            snapshot_kind=args.snapshot_kind,
            token=token,
            snapshot_limit=args.snapshot_limit,
        )
        source = remote_source_connection(str(manifest_path), len(manifest_items))
    elif args.manifest_url:
        token = os.getenv(args.auth_token_env) if args.auth_token_env else None
        if args.require_auth and not token:
            raise SystemExit(f"{args.auth_token_env} is required for {args.manifest_url}")
        series, manifest_items = build_series_from_manifest(
            manifest_url=args.manifest_url,
            base_url=args.base_url,
            snapshot_kind=args.snapshot_kind,
            token=token,
            snapshot_limit=args.snapshot_limit,
        )
        source = remote_source_connection(args.manifest_url, len(manifest_items))
    else:
        oracle_dir = Path(args.oracle_dir)
        snapshot_paths = discover_dated_graphs(oracle_dir)
        series = build_series(snapshot_paths)
        source = source_connection(snapshot_paths, oracle_dir)

    payload = RunRequest(
        eventText=args.event,
        scenarioCount=args.scenario_count,
        shots=args.shots,
        seed=args.seed,
        useOpenAi=args.use_openai,
    )

    if args.use_openai:
        log("Running OpenAI scenario planner")
        settings = get_settings()
        decision, series, scenarios, event_probability = await generate_openai_plan(settings, payload, series)
    else:
        log("Running deterministic scenario planner")
        decision = deterministic_decision(payload)
        scenarios = forecast_scenarios(series, decision.scenarioCount, decision.seed)
        event_probability = score_event(payload.eventText, scenarios, decision.dimensionWeights, None)

    log("Creating quantum circuit receipt")
    quantum_run = create_quantum_receipt(series, scenarios, decision.shots, decision.seed)
    return RunResponse(
        runId=run_id_for(payload.eventText, series, quantum_run.localRunId),
        sourceConnection=source,
        engineDecision=decision,
        weeklyPestelSeries=series,
        forecastScenarios=scenarios,
        eventProbability=event_probability,
        quantumRun=quantum_run,
        integrity=IntegrityNote(
            status="local_quantum_receipt",
            message=(
                "Circuit receipt generated from the full available dated ORACLE "
                "snapshot series. Attach a provider job ID when submitting this "
                "payload to hardware."
            ),
            hardwareClaimAllowed=False,
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build latest_run.json from local or deployed ORACLE graph snapshots.")
    parser.add_argument(
        "--oracle-dir",
        default=r"C:\Users\teres\PycharmProjects\oracle\frontend\public",
        help="Directory containing graph_YYYY-MM-DD.json ORACLE graph snapshots.",
    )
    parser.add_argument("--manifest-url", help="Authenticated ORACLE snapshot manifest URL, e.g. https://oraakkeli.metropolia.fi/api/snapshots")
    parser.add_argument("--manifest-file", help="Local JSON export from the ORACLE /api/snapshots endpoint.")
    parser.add_argument("--base-url", default="https://oraakkeli.metropolia.fi", help="Base URL for manifest snapshot paths.")
    parser.add_argument("--snapshot-kind", choices=["graph", "hierarchy"], default="graph")
    parser.add_argument("--snapshot-limit", type=int, help="Limit manifest snapshots for a quick connectivity test.")
    parser.add_argument("--auth-token-env", default="ORACLE_AUTH_TOKEN", help="Environment variable containing ORACLE bearer token.")
    parser.add_argument("--require-auth", action="store_true", help="Fail if auth token env var is missing.")
    parser.add_argument("--out", default=str(ROOT / "quantum_hardware" / "inputs" / "latest_run.json"))
    parser.add_argument("--event", default="Company becomes the biggest in its market after AI investment and market growth")
    parser.add_argument("--scenario-count", type=int, default=4)
    parser.add_argument("--shots", type=int, default=1024)
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--use-openai", action="store_true")
    args = parser.parse_args()

    result = asyncio.run(create_run(args))
    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    log(f"Writing payload: {output_path}")
    output_path.write_text(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote ORACLE-derived run payload: {output_path}")
    print(f"Snapshots: {result.sourceConnection.snapshotCount}")
    print("Weeks: " + ", ".join(state.weekId for state in result.weeklyPestelSeries))
    print("Clusters: " + ", ".join(str(state.clusterCount) for state in result.weeklyPestelSeries))
    print(f"Engine: {result.engineDecision.source} {result.engineDecision.model or ''}".strip())


if __name__ == "__main__":
    main()
