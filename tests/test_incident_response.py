import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


SERVICE_DIR = Path(__file__).resolve().parents[1] / "incident-response"
sys.path.insert(0, str(SERVICE_DIR))
import incident_service
from incident_service import create_app


@pytest.fixture
def incident_client(tmp_path):
    launched_incidents = []
    collected_alerts = []

    async def collect(alert, _start, _end):
        collected_alerts.append(alert)
        return {
            "logs": [{"line": "Order lookup completed", "status": 404}],
            "traces": [{"traceID": "abc123", "spans": 1}],
            "errors": [],
        }

    async def launch(incident_id, _db_path, _workspace):
        launched_incidents.append(incident_id)

    app = create_app(
        db_path=tmp_path / "incidents.sqlite3",
        evidence_collector=collect,
        assistant_launcher=launch,
        lookback_seconds=300,
    )
    app.state.launched_incidents = launched_incidents
    app.state.collected_alerts = collected_alerts
    with TestClient(app) as client:
        yield client


def test_grafana_alert_is_saved_with_endpoint_logs_and_traces(incident_client):
    payload = {
        "receiver": "incident-response",
        "status": "firing",
        "groupKey": "{}:{alertname=\"Order lookup 5xx responses\"}",
        "commonLabels": {"alertname": "Order lookup 5xx responses"},
        "alerts": [
            {
                "status": "firing",
                "labels": {"alertname": "Order lookup 5xx responses"},
                "annotations": {
                    "endpoint": "GET /api/orders/{order_id}",
                    "dashboard_url": "http://grafana/d/order-tracker-observability",
                },
                "startsAt": "2026-10-04T14:00:00Z",
                "endsAt": "0001-01-01T00:00:00Z",
                "fingerprint": "example-fingerprint",
            }
        ],
    }

    response = incident_client.post("/alerts", json=payload)

    assert response.status_code == 202
    assert response.json()["received"] == 1
    incident_id = response.json()["incident_ids"][0]
    incident = incident_client.get(f"/incidents/{incident_id}").json()
    assert incident["endpoint"] == "GET /api/orders/{order_id}"
    assert incident["dashboard_url"] == "http://grafana/d/order-tracker-observability"
    assert incident["evidence"]["logs"][0]["status"] == 404
    assert incident["evidence"]["traces"][0]["traceID"] == "abc123"
    assert incident["evidence_window"]["from"] == "2026-10-04T13:55:00+00:00"
    assert incident_client.get("/incidents").json()[0]["id"] == incident_id
    assert incident_client.app.state.launched_incidents == [incident_id]

    duplicate = incident_client.post("/alerts", json=payload)

    assert duplicate.status_code == 202
    assert duplicate.json()["incident_ids"] == [incident_id]
    assert len(incident_client.app.state.collected_alerts) == 1
    assert incident_client.app.state.launched_incidents == [incident_id]


def test_evidence_failure_does_not_drop_alert(tmp_path):
    launched_incidents = []

    async def fail(_alert, _start, _end):
        raise RuntimeError("backend unavailable")

    async def launch(incident_id, _db_path, _workspace):
        launched_incidents.append(incident_id)

    app = create_app(
        db_path=tmp_path / "incidents.sqlite3",
        evidence_collector=fail,
        assistant_launcher=launch,
    )
    with TestClient(app) as client:
        response = client.post("/alerts", json={"alerts": [{"status": "firing"}]})

    assert response.status_code == 202
    incident_id = response.json()["incident_ids"][0]
    incident = client.get(f"/incidents/{incident_id}").json()
    assert incident["evidence"]["logs"] == []
    assert "backend unavailable" in incident["evidence"]["errors"][0]
    assert launched_incidents == [incident_id]


def test_alert_payload_must_include_alerts_array(incident_client):
    response = incident_client.post("/alerts", json={"status": "firing"})

    assert response.status_code == 422


def test_resolved_alert_does_not_start_assistant(tmp_path):
    launched_incidents = []

    async def collect(_alert, _start, _end):
        return {"logs": [], "traces": [], "errors": []}

    async def launch(incident_id, _db_path, _workspace):
        launched_incidents.append(incident_id)

    app = create_app(
        db_path=tmp_path / "incidents.sqlite3",
        evidence_collector=collect,
        assistant_launcher=launch,
    )
    with TestClient(app) as client:
        response = client.post("/alerts", json={"alerts": [{"status": "resolved"}]})

    assert response.status_code == 202
    assert response.json()["received"] == 1
    assert launched_incidents == []


def test_copilot_runs_headlessly_with_workspace_scoped_arguments(monkeypatch):
    invocations = []

    class Process:
        returncode = 0

        async def wait(self):
            return None

    async def create_process(*args, **kwargs):
        invocations.append((args, kwargs))
        return Process()

    monkeypatch.setenv("COPILOT_GITHUB_TOKEN", "test-token")
    monkeypatch.setattr(incident_service.shutil, "which", lambda _command: "/usr/bin/copilot")
    monkeypatch.setattr(incident_service.asyncio, "create_subprocess_exec", create_process)

    asyncio.run(incident_service.launch_copilot("incident-id", "/data/incidents.sqlite3", "/workspace"))

    args, kwargs = invocations[0]
    assert args[0] == "/usr/bin/copilot"
    assert "--prompt" in args
    assert "--allow-all-tools" in args
    assert "--secret-env-vars" in args
    assert "COPILOT_GITHUB_TOKEN,GH_TOKEN,GITHUB_TOKEN" in args
    assert "--add-dir" in args
    assert "/workspace" in args
    assert "--no-ask-user" in args
    assert kwargs["stdout"] == asyncio.subprocess.DEVNULL
