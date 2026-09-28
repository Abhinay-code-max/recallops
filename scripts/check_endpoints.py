"""Calls every endpoint against a REAL running server (not an in-process TestClient --
start one first: `backend/.venv/Scripts/uvicorn app.main:app --app-dir backend`) and
prints a short summary of each response.

Usage: backend/.venv/Scripts/python scripts/check_endpoints.py [base_url]
       (base_url defaults to http://localhost:8000)
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "backend" / "data"

import httpx  # noqa: E402

BASE_URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def _demo_alert_payload(alert_id: str) -> dict:
    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))
    demo = next(a for a in demo_alerts if a["alert_id"] == alert_id)
    return {k: demo[k] for k in ("service", "severity", "title", "symptoms", "error_message", "log_snippet", "error_signature", "submitted_at")}


def main() -> int:
    try:
        client = httpx.Client(base_url=BASE_URL, timeout=60.0)
        client.get("/health")
    except httpx.ConnectError:
        print(f"Could not reach {BASE_URL} -- start the server first:")
        print("  backend/.venv/Scripts/uvicorn app.main:app --app-dir backend")
        return 1

    def summarize(label: str, response: httpx.Response, keys: list[str] | None = None) -> None:
        print(f"\n{label}: {response.status_code}")
        if response.status_code >= 400:
            print(f"  {response.text[:200]}")
            return
        try:
            body = response.json()
        except ValueError:
            print(f"  (non-JSON body, {len(response.content)} bytes)")
            return
        if keys is None:
            print(f"  {json.dumps(body)[:200]}")
            return
        if isinstance(body, list):
            print(f"  list of {len(body)} items; first: {json.dumps(body[0] if body else None)[:200]}")
            return
        summary = {k: body.get(k) for k in keys}
        print(f"  {json.dumps(summary, default=str)[:300]}")

    summarize("GET /health", client.get("/health"))
    summarize("POST /reset", client.post("/reset"))
    summarize("POST /seed", client.post("/seed"))
    summarize("GET /demo-alerts", client.get("/demo-alerts"))

    alert_response = client.post("/alert", json=_demo_alert_payload("DEMO-1"))
    summarize("POST /alert (DEMO-1)", alert_response, ["incident_id", "memory_state", "deduplicated", "degraded"])
    incident_id = alert_response.json()["incident_id"] if alert_response.status_code == 200 else None

    summarize("GET /incidents", client.get("/incidents"))
    if incident_id:
        summarize(f"GET /incidents/{incident_id}", client.get(f"/incidents/{incident_id}"), ["incident_id", "title", "outcome"])

        with client.stream("GET", f"/incidents/{incident_id}/briefing/stream") as stream:
            event_count = sum(1 for line in stream.iter_lines() if line.startswith("event:"))
        print(f"\nGET /incidents/{incident_id}/briefing/stream (SSE): {event_count} events")

        summarize(
            "POST /feedback",
            client.post("/feedback", json={"incident_id": incident_id, "fix_type": "increase_postgres_pool_size", "outcome": "worked"}),
            ["memories_stored"],
        )
        summarize(
            "POST /resolve",
            client.post("/resolve", json={"incident_id": incident_id, "resolver": "Priya Nair", "minutes_to_resolve": 9}),
            ["memories_stored"],
        )
        summarize("POST /chat", client.post("/chat", json={"incident_id": incident_id, "question": "Has this happened after a deploy before?"}), ["answer"])

    summarize("POST /compare", client.post("/compare", json={"alert": _demo_alert_payload("DEMO-2")}))
    summarize("GET /metrics", client.get("/metrics"), ["counts", "historical_avg_mttr_min", "simulated"])
    summarize("GET /insights", client.get("/insights"), ["patterns", "recurring", "reflect_summary"])

    client.close()
    print("\nAll endpoints reachable.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
