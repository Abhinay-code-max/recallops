import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import incidents
from app.main import app

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

pytestmark = pytest.mark.live


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/reset")
        c.post("/seed")
        yield c


@pytest.fixture(autouse=True)
def _reset_state():
    incidents.reset_live_state()
    yield
    incidents.reset_live_state()


def _post_demo_alert(client: TestClient, alert_id: str) -> dict:
    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))
    demo = next(a for a in demo_alerts if a["alert_id"] == alert_id)
    payload = {k: demo[k] for k in ("service", "severity", "title", "symptoms", "error_message", "log_snippet", "error_signature", "submitted_at")}
    return client.post("/alert", json=payload).json()


def test_feedback_changes_ranking_live(client: TestClient) -> None:
    alert = _post_demo_alert(client, "DEMO-1")
    incident_id = alert["incident_id"]
    assert alert["ranked_fixes"][0]["fix_type"] == "increase_postgres_pool_size"

    response = client.post(
        "/feedback",
        json={"incident_id": incident_id, "fix_type": "increase_postgres_pool_size", "outcome": "failed", "notes": "no effect"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ranked_fixes"][0]["fix_type"] != "increase_postgres_pool_size"
    assert any(w["kind"] == "failed_fix" for w in body["warnings"])
    assert body["memories_stored"] >= 0


def test_feedback_unknown_incident_404(client: TestClient) -> None:
    response = client.post("/feedback", json={"incident_id": "INC-999", "fix_type": "x", "outcome": "worked"})
    assert response.status_code == 404


def test_resolve_generates_postmortem_and_marks_resolved(client: TestClient) -> None:
    alert = _post_demo_alert(client, "DEMO-1")
    incident_id = alert["incident_id"]
    client.post("/feedback", json={"incident_id": incident_id, "fix_type": "increase_postgres_pool_size", "outcome": "worked"})

    response = client.post(
        "/resolve",
        json={"incident_id": incident_id, "resolver": "Priya Nair", "resolution_notes": "resized the pool", "minutes_to_resolve": 9},
    )
    assert response.status_code == 200
    body = response.json()
    postmortem = body["postmortem"]
    assert postmortem["root_cause"]
    assert postmortem["fix"]
    assert isinstance(postmortem["action_items"], list)

    detail = client.get(f"/incidents/{incident_id}").json()
    assert detail["outcome"] == "worked"
    assert detail["resolver"] == "Priya Nair"
    assert detail["minutes_to_resolve"] == 9
    assert detail["postmortem"]["root_cause"] == postmortem["root_cause"]


def test_resolve_unknown_incident_404(client: TestClient) -> None:
    response = client.post("/resolve", json={"incident_id": "INC-999", "resolver": "x"})
    assert response.status_code == 404


def test_get_demo_alerts_returns_five_with_all_capabilities(client: TestClient) -> None:
    response = client.get("/demo-alerts")
    body = response.json()
    assert len(body) == 5
    capabilities = {d["target_capability"] for d in body}
    assert capabilities == {"recall", "failure_warning", "reflect_pattern", "team_routing", "recurring_detector"}


def test_get_incidents_includes_seed_and_live(client: TestClient) -> None:
    alert = _post_demo_alert(client, "DEMO-1")
    rows = client.get("/incidents").json()
    ids = {r["incident_id"] for r in rows}
    assert "INC-002" in ids
    assert alert["incident_id"] in ids
    assert len(rows) == 23  # 22 seed + 1 live


def test_get_incident_detail_seed_has_string_postmortem(client: TestClient) -> None:
    detail = client.get("/incidents/INC-002").json()
    assert detail["incident_id"] == "INC-002"
    assert isinstance(detail["postmortem"], str)
    assert len(detail["fix_attempts"]) == 3


def test_get_incident_detail_unknown_404(client: TestClient) -> None:
    response = client.get("/incidents/INC-999")
    assert response.status_code == 404
