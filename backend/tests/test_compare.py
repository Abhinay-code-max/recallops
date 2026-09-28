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


def _demo_alert_payload(alert_id: str) -> dict:
    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))
    demo = next(a for a in demo_alerts if a["alert_id"] == alert_id)
    return {k: demo[k] for k in ("service", "severity", "title", "symptoms", "error_message", "log_snippet", "error_signature", "submitted_at")}


def test_compare_returns_both_sides(client: TestClient) -> None:
    response = client.post("/compare", json={"alert": _demo_alert_payload("DEMO-1")})
    assert response.status_code == 200
    body = response.json()

    assert body["without_memory"]["text"]
    assert body["with_memory"]["evidence"]
    assert body["with_memory"]["ranked_fixes"][0]["fix_type"] == "increase_postgres_pool_size"
    assert len(body["with_memory"]["sections"]["first_actions"]) == 3


def test_without_memory_never_cites_an_incident_id(client: TestClient) -> None:
    response = client.post("/compare", json={"alert": _demo_alert_payload("DEMO-1")})
    text = response.json()["without_memory"]["text"]
    assert "INC-" not in text


def test_compare_has_no_side_effects(client: TestClient) -> None:
    before = client.get("/incidents").json()

    client.post("/compare", json={"alert": _demo_alert_payload("DEMO-1")})
    client.post("/compare", json={"alert": _demo_alert_payload("DEMO-2")})

    after = client.get("/incidents").json()
    assert len(before) == len(after) == 22  # seed only -- no live incident created

    # dedupe state also untouched: the same alert submitted "again" via /alert right
    # after should NOT be seen as a duplicate of anything /compare created
    dup = incidents.find_recent_duplicate("payments-api", "postgres_pool_exhaustion", "2026-09-11T15:02:00Z")
    assert dup is None


def test_compare_with_unrelated_alert_has_empty_with_memory_evidence(client: TestClient) -> None:
    payload = {
        "alert": {
            "service": "payments-api",
            "severity": "SEV3",
            "title": "Office printer jam",
            "symptoms": "The office printer on the 3rd floor is jammed.",
            "error_message": "printer out of toner",
            "log_snippet": "PRINTER_JAM code=0x21",
            "error_signature": None,
            "submitted_at": "2026-09-11T15:02:00Z",
        }
    }
    response = client.post("/compare", json=payload)
    body = response.json()
    assert body["with_memory"]["evidence"] == []
    assert body["with_memory"]["ranked_fixes"] == []
    assert "no similar" in body["with_memory"]["sections"]["root_cause"].lower()
