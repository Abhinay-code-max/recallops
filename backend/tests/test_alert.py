"""Integration tests for POST /alert -- hits real Hindsight Cloud (this project's rule:
verify live, don't mock the memory layer away). Module-scoped client/seed so the ~10-15s
seed only runs once for the whole file.
"""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import incidents, ledger
from app import memory as memory_module
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
def _reset_live_state_between_tests():
    incidents.reset_live_state()
    yield
    incidents.reset_live_state()


def _demo_alert_payload(alert_id: str) -> dict:
    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))
    demo = next(a for a in demo_alerts if a["alert_id"] == alert_id)
    return {k: demo[k] for k in ("service", "severity", "title", "symptoms", "error_message", "log_snippet", "error_signature", "submitted_at")}


def test_matched_alert_returns_evidence_ranked_fixes_team_hint_recurrence(client: TestClient) -> None:
    response = client.post("/alert", json=_demo_alert_payload("DEMO-1"))
    assert response.status_code == 200
    body = response.json()

    assert body["memory_state"] == "matched"
    assert body["incident_id"].startswith("INC-0")
    assert body["deduplicated"] is False
    assert {e["incident_id"] for e in body["evidence"]} >= {"INC-002", "INC-009", "INC-017", "INC-021"}
    assert body["ranked_fixes"][0]["fix_type"] == "increase_postgres_pool_size"
    assert body["team_hint"]["person"] == "Priya Nair"
    assert body["recurrence"]["open_permanent_fix_incident_id"] == "INC-021"
    assert any(w["kind"] == "failed_fix" for w in body["warnings"])
    assert body["briefing_stream_url"] == f"/incidents/{body['incident_id']}/briefing/stream"
    assert body["degraded"] is False


def test_team_routing_hints_rahul_mehta(client: TestClient) -> None:
    response = client.post("/alert", json=_demo_alert_payload("DEMO-4"))
    body = response.json()
    assert body["team_hint"]["person"] == "Rahul Mehta"


def test_dedup_within_5_minutes_of_submitted_at(client: TestClient) -> None:
    payload = _demo_alert_payload("DEMO-1")
    first = client.post("/alert", json=payload).json()

    payload2 = dict(payload)
    payload2["submitted_at"] = "2026-09-11T15:04:00Z"  # 2 min after DEMO-1's submitted_at
    second = client.post("/alert", json=payload2).json()

    assert second["deduplicated"] is True
    assert second["incident_id"] == first["incident_id"]


def test_no_dedup_when_demo_alerts_are_days_apart(client: TestClient) -> None:
    first = client.post("/alert", json=_demo_alert_payload("DEMO-1")).json()
    second = client.post("/alert", json=_demo_alert_payload("DEMO-2")).json()
    assert second["deduplicated"] is False
    assert second["incident_id"] != first["incident_id"]


def test_no_match_for_unrelated_nonsense_alert(client: TestClient) -> None:
    payload = {
        "service": "payments-api",
        "severity": "SEV3",
        "title": "Office printer jam",
        "symptoms": "The office printer on the 3rd floor is jammed and printing blank pages.",
        "error_message": "printer out of toner",
        "log_snippet": "PRINTER_JAM code=0x21 tray=2",
        "error_signature": None,
        "submitted_at": "2026-09-11T15:02:00Z",
    }
    response = client.post("/alert", json=payload)
    body = response.json()
    assert body["memory_state"] == "no_match"
    assert body["evidence"] == []
    assert body["ranked_fixes"] == []
    assert body["warnings"] == []
    assert body["team_hint"] is None
    assert body["recurrence"] is None


def test_empty_memory_state_when_no_ledger(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ledger, "read_ledger", lambda: None)
    response = client.post("/alert", json=_demo_alert_payload("DEMO-1"))
    body = response.json()
    assert body["memory_state"] == "empty"
    assert body["evidence"] == []
    assert body["ranked_fixes"] == []


def test_hindsight_down_returns_degraded_but_still_answers(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def _always_degraded(*args, **kwargs):
        return memory_module.RecallOutcome(hits=[], degraded=True)

    monkeypatch.setattr(memory_module, "recall_merged", _always_degraded)

    response = client.post("/alert", json=_demo_alert_payload("DEMO-1"))
    assert response.status_code == 200  # never a 500, even with Hindsight unavailable
    body = response.json()
    assert body["degraded"] is True
    assert body["memory_state"] in ("no_match", "empty")  # no hits came back -> can't be "matched"
    assert body["incident_id"]
    assert body["ranked_fixes"] == []


def test_secrets_masked_in_stored_and_returned_log(client: TestClient) -> None:
    payload = _demo_alert_payload("DEMO-1")
    payload["log_snippet"] += " Authorization: Bearer demo-token-0000"
    response = client.post("/alert", json=payload)
    body = response.json()

    assert "demo-token-0000" not in body["alert"]["log_snippet"]

    incident = incidents.get_incident(body["incident_id"])
    assert "demo-token-0000" not in (incident.get("log_snippet") or "")
