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


@pytest.mark.live
def test_get_insights_shape_and_cache() -> None:
    with TestClient(app) as client:
        client.post("/reset")
        client.post("/seed")

        first = client.get("/insights")
        assert first.status_code == 200
        body = first.json()

        assert len(body["patterns"]) >= 10
        assert any(r["recurrence"]["occurrence_number"] >= 2 for r in body["recurring"])
        assert body["open_permanent_fixes"] == [
            {
                "incident_id": "INC-021",
                "title": "Postgres connection pool exhaustion recurs a fourth time after v2.5.0 Friday deploy",
                "message": body["open_permanent_fixes"][0]["message"],
            }
        ]
        assert isinstance(body["reflect_summary"], str) and body["reflect_summary"]
        # numbers must come from the deterministic fields, never parsed from reflect_summary
        assert body["fix_speed_comparison"]["sample_size"] > 0

        second = client.get("/insights").json()
        assert second == body  # cached, identical


@pytest.mark.live
def test_insights_cache_invalidated_by_feedback_and_reset() -> None:
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
        assert after_feedback != before  # cache was invalidated, recomputed with the new feedback

        client.post("/reset")
        after_reset = client.get("/insights").json()
        assert after_reset["open_permanent_fixes"] == before["open_permanent_fixes"]  # back to seed-only state
