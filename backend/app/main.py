from __future__ import annotations

import hashlib
import time
from typing import Annotated

import httpx
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import Settings, get_settings
from app.models import (
    BuildSeriesRequest,
    BuildSeriesResponse,
    IntegrityNote,
    RunRequest,
    RunResponse,
)
from app.services.event_scoring import score_event
from app.services.forecast import forecast_scenarios
from app.services.openai_planner import deterministic_decision, generate_openai_plan
from app.services.pestel import extract_weekly_pestel
from app.services.quantum_emulator import create_quantum_receipt
from app.services.run_store import get_run, save_run
from app.services.source_adapter import SourceAdapter

app = FastAPI(
    title="Q-FIN Scenario Engine",
    version="0.1.0",
    description="Standalone market intelligence -> PESTEL -> temporal scenario -> quantum receipt API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def adapter(settings: Annotated[Settings, Depends(get_settings)]) -> SourceAdapter:
    return SourceAdapter(settings)


@app.get("/")
async def root():
    return {
        "service": "Q-FIN Scenario Engine API",
        "docs": "/docs",
        "health": "/api/health",
        "frontend": "http://127.0.0.1:5179",
        "message": "Open the frontend URL in your browser. This port serves the API only.",
    }


@app.get("/api/health")
async def health(settings: Annotated[Settings, Depends(get_settings)]):
    return {
        "status": "ok",
        "quantumReceipt": "local_quantum_circuit_receipt",
        "hardwareJobSubmitted": False,
        "sourceConfigured": settings.has_external_source,
        "sourceBaseUrl": settings.source_base_url,
        "engineConfigured": True,
        "engineMode": "Q-FIN pipeline",
    }


@app.get("/api/source/snapshots")
async def source_snapshots(source: Annotated[SourceAdapter, Depends(adapter)]):
    try:
        snapshots = await source.list_snapshots()
        return {
            "sourceConnection": await source.connection(),
            "snapshots": snapshots,
        }
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not reach external source: {exc}") from exc


@app.get("/api/source/snapshots/{snapshot_id}")
async def source_snapshot(snapshot_id: str, source: Annotated[SourceAdapter, Depends(adapter)]):
    try:
        meta, snapshot = await source.get_snapshot(snapshot_id)
        return {"meta": meta, "snapshot": snapshot}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch source snapshot: {exc}") from exc


async def build_series_from_request(payload: BuildSeriesRequest, source: SourceAdapter):
    metas_and_snapshots = []
    if payload.snapshotUrls:
        for index, url in enumerate(payload.snapshotUrls):
            metas_and_snapshots.append(await source.get_snapshot_by_url(url, index))
    else:
        available = await source.list_snapshots()
        requested = payload.snapshotIds or [item.id for item in available]
        for snapshot_id in requested:
            metas_and_snapshots.append(await source.get_snapshot(snapshot_id))

    series = [
        extract_weekly_pestel(meta.id, meta.label, snapshot, meta.source)
        for meta, snapshot in metas_and_snapshots
    ]
    series.sort(key=lambda item: item.weekId)
    return BuildSeriesResponse(
        sourceConnection=await source.connection(),
        weeklyPestelSeries=series,
    )


@app.post("/api/series/build", response_model=BuildSeriesResponse)
async def build_series(payload: BuildSeriesRequest, source: Annotated[SourceAdapter, Depends(adapter)]):
    try:
        return await build_series_from_request(payload, source)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch source data: {exc}") from exc


@app.post("/api/simulate", response_model=RunResponse)
@app.post("/api/run", response_model=RunResponse)
async def run_engine(
    payload: RunRequest,
    source: Annotated[SourceAdapter, Depends(adapter)],
    settings: Annotated[Settings, Depends(get_settings)],
):
    try:
        series_response = await build_series_from_request(
            BuildSeriesRequest(snapshotIds=payload.snapshotIds, snapshotUrls=payload.snapshotUrls),
            source,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Could not fetch source data: {exc}") from exc

    series = series_response.weeklyPestelSeries
    if payload.useOpenAi:
        try:
            decision, series, scenarios, event_probability = await generate_openai_plan(settings, payload, series)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail=f"Q-FIN probability call failed: {exc.response.text}") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"Q-FIN probability call failed: {exc}") from exc
    else:
        decision = deterministic_decision(payload)
        scenarios = forecast_scenarios(series, decision.scenarioCount, decision.seed)
        event_probability = score_event(payload.eventText, scenarios, decision.dimensionWeights, None)
    quantum_run = create_quantum_receipt(series, scenarios, decision.shots, decision.seed)
    run_fingerprint = hashlib.sha256(
        f"{time.time()}-{payload.eventText}-{decision.seed}-{quantum_run.localRunId}".encode("utf-8")
    ).hexdigest()[:14]

    result = RunResponse(
        runId=f"run-{run_fingerprint}",
        sourceConnection=series_response.sourceConnection,
        engineDecision=decision,
        weeklyPestelSeries=series,
        forecastScenarios=scenarios,
        eventProbability=event_probability,
        quantumRun=quantum_run,
        integrity=IntegrityNote(
            status="local_quantum_receipt",
            message=(
                "This quantum circuit receipt was generated from the PESTEL-weighted scenario path. "
                "Link a hardware provider job ID to upgrade it to a verified run."
            ),
            hardwareClaimAllowed=False,
        ),
    )
    save_run(result)
    return result


@app.get("/api/simulations/{run_id}", response_model=RunResponse)
@app.get("/api/runs/{run_id}", response_model=RunResponse)
async def run_result(run_id: str):
    result = get_run(run_id)
    if not result:
        raise HTTPException(status_code=404, detail=f"Run {run_id} was not found")
    return result
