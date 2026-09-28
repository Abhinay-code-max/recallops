"""POST /chat sanity check: runs 4 questions against a DEMO-1 incident and prints
answer + cited ids + evidence ids for each. The first 3 should return real evidence
(their questions are all about the payments-api pool-exhaustion pattern DEMO-1
matches); the 4th ("What is the weather in Delhi?") should say it has no relevant
history and cite nothing.

Usage: backend/.venv/Scripts/python scripts/chat_sanity.py
"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

DATA_DIR = REPO_ROOT / "backend" / "data"

QUESTIONS = [
    "Has this happened after a deploy before?",
    "Who fixed this last time?",
    "What should I try first?",
    "What is the weather in Delhi?",
]


def _demo_alert_payload(alert_id: str) -> dict:
    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))
    demo = next(a for a in demo_alerts if a["alert_id"] == alert_id)
    return {k: demo[k] for k in ("service", "severity", "title", "symptoms", "error_message", "log_snippet", "error_signature", "submitted_at")}


def main() -> int:
    with TestClient(app) as client:
        client.post("/reset")
        client.post("/seed")
        incident_id = client.post("/alert", json=_demo_alert_payload("DEMO-1")).json()["incident_id"]
        print(f"incident_id: {incident_id}\n")

        for question in QUESTIONS:
            response = client.post("/chat", json={"incident_id": incident_id, "question": question})
            body = response.json()
            evidence_ids = [e["incident_id"] for e in body["evidence"]]
            from app.analysis import extract_incident_ids

            cited_ids = sorted(extract_incident_ids(body["answer"]))
            print(f"Q: {question}")
            print(f"A: {body['answer']}")
            print(f"cited_ids: {cited_ids}")
            print(f"evidence_ids: {evidence_ids}")
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
