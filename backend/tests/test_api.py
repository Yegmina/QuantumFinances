from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.services.forecast import forecast_scenarios
from app.services.pestel import extract_weekly_pestel

client = TestClient(app)


def test_health_reports_no_hardware_submission():
    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["hardwareJobSubmitted"] is False


def test_sample_snapshot_listing():
    response = client.get("/api/source/snapshots")
    assert response.status_code == 200
    body = response.json()
    assert body["sourceConnection"]["mode"] == "sample"
    assert len(body["snapshots"]) >= 3


def test_series_build_contract_and_normalization():
    response = client.post("/api/series/build", json={})
    assert response.status_code == 200
    body = response.json()
    series = body["weeklyPestelSeries"]
    assert len(series) >= 3
    assert [item["weekId"] for item in series] == sorted(item["weekId"] for item in series)
    for state in series:
        for value in state["pestel"].values():
            assert 0 <= value <= 1


def test_run_returns_full_contract():
    response = client.post(
        "/api/run",
        json={
            "eventText": "Company becomes biggest after AI investment and market growth",
            "scenarioCount": 4,
            "shots": 1024,
            "seed": 17,
            "useOpenAi": False,
            "dimensionWeights": {
                "political": 0.1,
                "economic": 0.45,
                "social": 0.05,
                "technological": 0.25,
                "environmental": 0.05,
                "legal": 0.1,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["runId"].startswith("run-")
    assert body["engineDecision"]["source"] == "local_baseline"
    assert body["integrity"]["status"] == "local_quantum_receipt"
    assert body["quantumRun"]["hardwareJobSubmitted"] is False
    assert body["quantumRun"]["executionMode"] == "circuit_receipt"
    assert body["quantumRun"]["localRunId"].startswith("qrun-")
    assert sum(body["quantumRun"]["counts"].values()) == 1024
    assert 0 <= body["eventProbability"]["probability"] <= 1
    scenario_total = sum(item["probability"] for item in body["forecastScenarios"])
    assert abs(scenario_total - 1) < 0.000001

    lookup = client.get(f"/api/runs/{body['runId']}")
    assert lookup.status_code == 200
    assert lookup.json()["runId"] == body["runId"]


def test_source_adapter_missing_snapshot_returns_404():
    response = client.get("/api/source/snapshots/not-real")
    assert response.status_code == 404

    series_response = client.post("/api/series/build", json={"snapshotIds": ["not-real"]})
    assert series_response.status_code == 404

    run_response = client.post("/api/run", json={"snapshotIds": ["not-real"], "useOpenAi": False})
    assert run_response.status_code == 404


def test_forecast_probabilities_sum_to_one_with_direct_service():
    raw = {
        "levels": {
            "L2": {
                "clusterSizes": [10],
                "graph": {
                    "nodes": [{"id": 0, "text": "market growth ai policy regulation"}],
                    "edges": [],
                },
            }
        }
    }
    series = [
        extract_weekly_pestel("w0", "Week 0", raw, "sample"),
        extract_weekly_pestel("w1", "Week 1", raw, "sample"),
    ]
    scenarios = forecast_scenarios(series, 5, 11)
    assert abs(sum(item.probability for item in scenarios) - 1) < 0.000001
