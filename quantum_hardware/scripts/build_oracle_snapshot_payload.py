from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


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
    oracle_dir = Path(args.oracle_dir)
    snapshot_paths = discover_dated_graphs(oracle_dir)
    series = build_series(snapshot_paths)
    payload = RunRequest(
        eventText=args.event,
        scenarioCount=args.scenario_count,
        shots=args.shots,
        seed=args.seed,
        useOpenAi=args.use_openai,
    )

    if args.use_openai:
        settings = get_settings()
        decision, series, scenarios, event_probability = await generate_openai_plan(settings, payload, series)
    else:
        decision = deterministic_decision(payload)
        scenarios = forecast_scenarios(series, decision.scenarioCount, decision.seed)
        event_probability = score_event(payload.eventText, scenarios, decision.dimensionWeights, None)

    quantum_run = create_quantum_receipt(series, scenarios, decision.shots, decision.seed)
    return RunResponse(
        runId=run_id_for(payload.eventText, series, quantum_run.localRunId),
        sourceConnection=source_connection(snapshot_paths, oracle_dir),
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
    parser = argparse.ArgumentParser(description="Build latest_run.json from local dated ORACLE graph snapshots.")
    parser.add_argument(
        "--oracle-dir",
        default=r"C:\Users\teres\PycharmProjects\oracle\frontend\public",
        help="Directory containing graph_YYYY-MM-DD.json ORACLE graph snapshots.",
    )
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
    output_path.write_text(json.dumps(result.model_dump(mode="json"), indent=2, sort_keys=True), encoding="utf-8")

    print(f"Wrote ORACLE-derived run payload: {output_path}")
    print(f"Snapshots: {result.sourceConnection.snapshotCount}")
    print("Weeks: " + ", ".join(state.weekId for state in result.weeklyPestelSeries))
    print("Clusters: " + ", ".join(str(state.clusterCount) for state in result.weeklyPestelSeries))
    print(f"Engine: {result.engineDecision.source} {result.engineDecision.model or ''}".strip())


if __name__ == "__main__":
    main()
