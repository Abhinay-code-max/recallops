"""POST /reset must clear the insights cache, briefing cache, live incidents, and
counters (INC-id counter, memories_stored) -- Prompt 4 item 5."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import incidents
from app.main import app
from app.routes import briefing, insights

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

pytestmark = pytest.mark.live


@pytest.fixture(autouse=True)
def _reset_state():
    incidents.reset_live_state()
    briefing.clear_cache()
    insights.clear_cache()
    yield
    incidents.reset_live_state()
    briefing.clear_cache()
    insights.clear_cache()


def _demo_alert_payload(alert_id: str) -> dict:
    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))
    demo = next(a for a in demo_alerts if a["alert_id"] == alert_id)
    return {k: demo[k] for k in ("service", "severity", "title", "symptoms", "error_message", "log_snippet", "error_signature", "submitted_at")}


def test_reset_clears_briefing_cache_insights_cache_live_state_and_counters() -> None:
    with TestClient(app) as client:
        client.post("/reset")
        client.post("/seed")

        # build up state: a live incident, its briefing cache, feedback, and the
        # insights cache (all recomputed/populated by this point)
        incident_id = client.post("/alert", json=_demo_alert_payload("DEMO-1")).json()["incident_id"]
        client.get(f"/incidents/{incident_id}/briefing/stream")  # populates briefing cache
        client.post("/feedback", json={"incident_id": incident_id, "fix_type": "increase_postgres_pool_size", "outcome": "worked"})
        client.get("/insights")  # populates insights cache

        assert briefing._briefing_cache  # non-empty
        assert insights._cache is not None
        assert incidents.live_incidents()
        assert incidents.memories_stored_count() > 0
        assert incidents.next_incident_id() != "INC-023"  # counter has advanced (this call also bumps it further)

        client.post("/reset")

        assert briefing._briefing_cache == {}
        assert insights._cache is None
        assert incidents.live_incidents() == []
        assert incidents.memories_stored_count() == 0
        assert incidents.get_incident(incident_id) is None
        assert incidents.next_incident_id() == "INC-023"  # counter reset back to the start
