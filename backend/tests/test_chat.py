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


def test_chat_answers_deploy_question_for_demo1(client: TestClient) -> None:
    incident_id = client.post("/alert", json=_demo_alert_payload("DEMO-1")).json()["incident_id"]

    response = client.post("/chat", json={"incident_id": incident_id, "question": "Has this happened after a deploy before?"})
    assert response.status_code == 200
    body = response.json()

    assert body["answer"]
    evidence_ids = {e["incident_id"] for e in body["evidence"]}
    assert evidence_ids & {"INC-002", "INC-009", "INC-017", "INC-021"}


def test_chat_citation_guard_only_cites_recalled_evidence(client: TestClient) -> None:
    incident_id = client.post("/alert", json=_demo_alert_payload("DEMO-1")).json()["incident_id"]
    response = client.post("/chat", json={"incident_id": incident_id, "question": "What fix worked most often?"})
    body = response.json()

    from app.analysis import extract_incident_ids

    cited = extract_incident_ids(body["answer"])
    evidence_ids = {e["incident_id"] for e in body["evidence"]}
    assert cited <= evidence_ids


def test_chat_without_incident_id(client: TestClient) -> None:
    response = client.post("/chat", json={"question": "Has payments-api had connection pool problems before?"})
    assert response.status_code == 200
    body = response.json()
    assert body["answer"]


def test_chat_unknown_incident_404(client: TestClient) -> None:
    response = client.post("/chat", json={"incident_id": "INC-999", "question": "anything"})
    assert response.status_code == 404


def test_chat_unrelated_question_gives_template_style_answer(client: TestClient) -> None:
    response = client.post("/chat", json={"question": "What's the best pizza topping?"})
    body = response.json()
    assert body["evidence"] == []
    assert body["answer"]  # still answers something, never a 500
