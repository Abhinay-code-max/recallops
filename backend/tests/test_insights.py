import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from app import incidents
from app.main import app
from app.routes import insights


@pytest.fixture(autouse=True)
def _reset_state():
    incidents.reset_live_state()
    insights.clear_cache()
    yield
    incidents.reset_live_state()
    insights.clear_cache()


def _poll_until_not_pending(client: TestClient, timeout_s: float = 60.0) -> dict:
    deadline = time.time() + timeout_s
    body = client.get("/insights").json()
    while body["reflect_status"] == "pending" and time.time() < deadline:
        time.sleep(1)
        body = client.get("/insights").json()
    return body


def test_deterministic_facts_are_pure_and_offline() -> None:
    # No Hindsight/Groq involved -- these are plain structured-data computations.
    patterns = incidents.compute_patterns()
    pool_pattern = next(p for p in patterns if p["title"] == "Pool exhaustion friday deploy")
    assert pool_pattern["frequency"] == 4
    assert pool_pattern["interval_days"] == 35.0
    assert set(pool_pattern["incident_ids"]) == {"INC-002", "INC-009", "INC-017", "INC-021"}

    open_fixes = incidents.compute_open_permanent_fixes()
    assert [f["incident_id"] for f in open_fixes] == ["INC-021"]

    team = incidents.compute_team_knowledge()
    priya = next(t for t in team if t["person"] == "Priya Nair")
    assert "postgres pool exhaustion 4 times" in priya["summary"]

    fix_speed = incidents.compute_fix_speed_comparison()
    assert fix_speed["sample_size"] > 0
    assert fix_speed["first_fix_rollback_avg_min"] is not None


def test_insights_responds_fast_even_while_reflect_is_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prompt 4b item 1: GET /insights must respond in well under 1s even while
    reflect() is slow -- entirely offline, via a mocked reflect that sleeps."""

    async def _slow_reflect(*args, **kwargs):
        await asyncio.sleep(5)
        return "should never be awaited by the route itself"

    monkeypatch.setattr(insights.memory, "reflect", _slow_reflect)

    with TestClient(app) as client:
        insights.invalidate()  # starts the background task with the slow mock
        t0 = time.time()
        response = client.get("/insights")
        elapsed = time.time() - t0

        assert response.status_code == 200
        assert elapsed < 1.0
        body = response.json()
        assert body["reflect_status"] in ("pending", "ready", "failed")
        assert len(body["patterns"]) >= 10  # deterministic facts are present immediately


@pytest.mark.live
def test_get_insights_shape_reflect_eventually_ready() -> None:
    with TestClient(app) as client:
        client.post("/reset")
        client.post("/seed")

        immediate = client.get("/insights")
        assert immediate.status_code == 200
        immediate_body = immediate.json()
        assert immediate_body["reflect_status"] in ("pending", "ready")
        assert len(immediate_body["patterns"]) >= 10  # present even before reflect finishes

        body = _poll_until_not_pending(client)
        assert body["reflect_status"] == "ready"
        assert isinstance(body["reflect_summary"], str) and body["reflect_summary"]

        assert any(r["recurrence"]["occurrence_number"] >= 2 for r in body["recurring"])
        assert body["open_permanent_fixes"] == [
            {
                "incident_id": "INC-021",
                "title": "Postgres connection pool exhaustion recurs a fourth time after v2.5.0 Friday deploy",
                "message": body["open_permanent_fixes"][0]["message"],
            }
        ]
        assert body["fix_speed_comparison"]["sample_size"] > 0

        second = client.get("/insights").json()
        assert second == body  # cached, identical while nothing has changed


@pytest.mark.live
def test_insights_deterministic_fields_change_on_feedback_and_reset() -> None:
    with TestClient(app) as client:
        client.post("/reset")
        client.post("/seed")

        import json
        from pathlib import Path

        demo_alerts = json.loads((Path(__file__).resolve().parent.parent / "data" / "demo_alerts.json").read_text(encoding="utf-8"))
        demo1 = next(a for a in demo_alerts if a["alert_id"] == "DEMO-1")
        payload = {k: demo1[k] for k in ("service", "severity", "title", "symptoms", "error_message", "log_snippet", "error_signature", "submitted_at")}
        incident_id = client.post("/alert", json=payload).json()["incident_id"]

        before = client.get("/insights").json()
        client.post("/feedback", json={"incident_id": incident_id, "fix_type": "increase_postgres_pool_size", "outcome": "worked"})
        after_feedback = client.get("/insights").json()
        assert after_feedback["patterns"] != before["patterns"]  # the new live incident joined its pattern group
        assert after_feedback["reflect_status"] == "pending"  # invalidated, restarted

        client.post("/reset")
        after_reset = client.get("/insights").json()
        assert after_reset["open_permanent_fixes"] == before["open_permanent_fixes"]  # back to seed-only state
