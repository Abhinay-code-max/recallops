import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import incidents
from app.main import app

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(autouse=True)
def _reset_state():
    incidents.reset_live_state()
    yield
    incidents.reset_live_state()


def test_metrics_shape_from_seed_data_only() -> None:
    # No /seed call, no Hindsight touched -- real_series/historical_avg_mttr_min come
    # straight from the static seed_incidents.json/seed_metrics.json files.
    with TestClient(app) as client:
        response = client.get("/metrics")
    assert response.status_code == 200
    body = response.json()

    assert body["counts"]["incidents_handled"] == 22
    assert body["counts"]["memories_stored"] == 60
    assert body["simulated"] is True
    assert len(body["real_series"]) == 22
    assert all(point["live"] is False for point in body["real_series"])
    assert len(body["simulated_series"]) == 22
    assert 15 < body["historical_avg_mttr_min"] < 25  # ~19.2, see docs/HINDSIGHT_NOTES.md calibration


def test_real_series_matches_seed_incidents_exactly() -> None:
    seed_incidents = json.loads((DATA_DIR / "seed_incidents.json").read_text(encoding="utf-8"))
    with TestClient(app) as client:
        body = client.get("/metrics").json()
    for point, inc in zip(body["real_series"], seed_incidents):
        assert point["incident_id"] == inc["incident_id"]
        assert point["mttr_min"] == inc["total_minutes_to_resolve"]


@pytest.mark.live
def test_metrics_includes_resolved_live_incident() -> None:
    with TestClient(app) as client:
        client.post("/reset")
        client.post("/seed")

        demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))
        demo1 = next(a for a in demo_alerts if a["alert_id"] == "DEMO-1")
        payload = {k: demo1[k] for k in ("service", "severity", "title", "symptoms", "error_message", "log_snippet", "error_signature", "submitted_at")}
        incident_id = client.post("/alert", json=payload).json()["incident_id"]

        before = client.get("/metrics").json()

        client.post("/feedback", json={"incident_id": incident_id, "fix_type": "increase_postgres_pool_size", "outcome": "worked"})
        client.post("/resolve", json={"incident_id": incident_id, "resolver": "Priya Nair", "minutes_to_resolve": 9})

        after = client.get("/metrics").json()

    # incidents_handled already counted this incident as of the /alert call (before);
    # feedback/resolve don't create a new incident, just resolve the existing one.
    assert after["counts"]["incidents_handled"] == before["counts"]["incidents_handled"] == 23
    assert after["counts"]["memories_stored"] > before["counts"]["memories_stored"]

    live_points = [p for p in after["real_series"] if p["live"]]
    assert len(live_points) == 1
    assert live_points[0]["incident_id"] == incident_id
    assert live_points[0]["mttr_min"] == 9
