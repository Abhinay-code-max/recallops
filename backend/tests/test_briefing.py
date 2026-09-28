import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import incidents
from app.llm import LLMResult
from app.main import app
from app.routes import briefing

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        c.post("/reset")
        c.post("/seed")
        yield c


@pytest.fixture(autouse=True)
def _reset_state():
    incidents.reset_live_state()
    briefing.clear_cache()
    yield
    incidents.reset_live_state()
    briefing.clear_cache()


def _demo_alert_payload(alert_id: str) -> dict:
    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))
    demo = next(a for a in demo_alerts if a["alert_id"] == alert_id)
    return {k: demo[k] for k in ("service", "severity", "title", "symptoms", "error_message", "log_snippet", "error_signature", "submitted_at")}


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.strip().split("\n\n"):
        lines = block.strip().splitlines()
        event = next(l.split(": ", 1)[1] for l in lines if l.startswith("event:"))
        data = json.loads(next(l.split(": ", 1)[1] for l in lines if l.startswith("data:")))
        events.append((event, data))
    return events


def test_matched_incident_streams_and_cites_only_evidence(client: TestClient) -> None:
    alert_response = client.post("/alert", json=_demo_alert_payload("DEMO-1")).json()
    incident_id = alert_response["incident_id"]
    evidence_ids = {e["incident_id"] for e in alert_response["evidence"]}

    response = client.get(f"/incidents/{incident_id}/briefing/stream")
    assert response.status_code == 200
    events = _parse_sse(response.text)

    kinds = [e for e, _ in events]
    assert kinds[0] == "token"
    assert kinds[-2] == "sections"
    assert kinds[-1] == "done"

    sections = next(d for e, d in events if e == "sections")
    assert set(sections.keys()) == {"root_cause", "blast_radius", "first_actions", "last_fixed_by"}
    assert len(sections["first_actions"]) == 3

    cited = next(d for e, d in events if e == "done")["cited_incident_ids"]
    assert set(cited) <= evidence_ids  # hallucination guard: only cites recalled evidence


def test_caches_per_incident_id(client: TestClient) -> None:
    alert_response = client.post("/alert", json=_demo_alert_payload("DEMO-2")).json()
    incident_id = alert_response["incident_id"]

    first = _parse_sse(client.get(f"/incidents/{incident_id}/briefing/stream").text)
    second = _parse_sse(client.get(f"/incidents/{incident_id}/briefing/stream").text)

    first_sections = next(d for e, d in first if e == "sections")
    second_sections = next(d for e, d in second if e == "sections")
    assert first_sections == second_sections


def test_unknown_incident_returns_404(client: TestClient) -> None:
    response = client.get("/incidents/INC-999/briefing/stream")
    assert response.status_code == 404


def test_llm_down_falls_back_to_template(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    alert_response = client.post("/alert", json=_demo_alert_payload("DEMO-1")).json()
    incident_id = alert_response["incident_id"]

    async def _always_degraded(*args, **kwargs):
        return LLMResult(text="", degraded=True)

    monkeypatch.setattr(briefing.llm, "complete", _always_degraded)

    events = _parse_sse(client.get(f"/incidents/{incident_id}/briefing/stream").text)
    sections = next(d for e, d in events if e == "sections")
    cited = next(d for e, d in events if e == "done")["cited_incident_ids"]

    assert cited == []  # template never cites an incident ID
    assert sections["root_cause"]  # still a usable briefing, not an empty/broken one


def test_hallucination_guard_falls_back_after_two_bad_citations(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    alert_response = client.post("/alert", json=_demo_alert_payload("DEMO-1")).json()
    incident_id = alert_response["incident_id"]

    bad_json = json.dumps(
        {
            "root_cause": "Caused by INC-999, an incident that was never recalled.",
            "blast_radius": "everything",
            "first_actions": ["a", "b", "c"],
            "last_fixed_by": None,
        }
    )

    async def _cites_unrecalled_incident(*args, **kwargs):
        return LLMResult(text=bad_json, degraded=False, model_used="fake", parsed=json.loads(bad_json))

    monkeypatch.setattr(briefing.llm, "complete", _cites_unrecalled_incident)

    events = _parse_sse(client.get(f"/incidents/{incident_id}/briefing/stream").text)
    sections = next(d for e, d in events if e == "sections")
    cited = next(d for e, d in events if e == "done")["cited_incident_ids"]

    assert "INC-999" not in json.dumps(sections)  # guard rejected the hallucinated citation
    assert cited == []


def test_empty_memory_state_template_says_no_history() -> None:
    incidents.next_incident_id()
    incidents.record_alert(
        "INC-023",
        {"title": "First ever alert", "service": "payments-api", "severity": "SEV1", "submitted_at": "2026-09-11T15:02:00Z"},
        [],
        memory_state="empty",
    )
    sections = briefing._template_sections(incidents.get_incident("INC-023"))
    assert "no incident history" in sections["root_cause"].lower() or "first incident" in sections["root_cause"].lower()
    assert sections["last_fixed_by"] is None
    # generic safe checklist: no incident-specific claims, just standard first-response steps
    assert len(sections["first_actions"]) == 3
    for action in sections["first_actions"]:
        assert "INC-" not in action


def test_no_match_template_says_no_similar_incident() -> None:
    incidents.next_incident_id()
    incidents.record_alert(
        "INC-023",
        {"title": "Weird one-off alert", "service": "payments-api", "severity": "SEV1", "submitted_at": "2026-09-11T15:02:00Z"},
        [],
        memory_state="no_match",
    )
    sections = briefing._template_sections(incidents.get_incident("INC-023"))
    assert "no similar" in sections["root_cause"].lower()
    assert sections["last_fixed_by"] is None
