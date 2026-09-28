"""Demo flow: resets, runs DEMO-1, marks the rollback Failed on that incident, then runs
DEMO-2 (a fresh alert, same pattern) and prints both rankings side by side -- this is
the spec's "learning" demo beat: mark a fix Failed, fire a similar alert, watch the
ranking (and warnings) change live.

Usage: backend/.venv/Scripts/python scripts/demo_flow.py
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

DATA_DIR = REPO_ROOT / "backend" / "data"
FAILED_FIX_TYPE = "rollback_to_previous_deploy"


def _demo_alert_payload(alert_id: str) -> dict:
    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))
    demo = next(a for a in demo_alerts if a["alert_id"] == alert_id)
    return {k: demo[k] for k in ("service", "severity", "title", "symptoms", "error_message", "log_snippet", "error_signature", "submitted_at")}


def _print_ranking(label: str, ranked_fixes: list[dict]) -> None:
    print(f"\n--- {label} ---")
    if not ranked_fixes:
        print("  (no ranked fixes)")
        return
    for fix in ranked_fixes:
        print(
            f"  {fix['rank']}. {fix['fix_type']:<28} score={fix['score']:+.4f}  "
            f"similarity={fix['similarity']:.3f}  worked={fix['worked']} partial={fix['partial']} "
            f"failed={fix['failed']} recent_failures={fix['recent_failures']}"
        )


def main() -> int:
    with TestClient(app) as client:
        print("--- reset ---")
        print(client.post("/reset").json())

        print("\n--- seed ---")
        print(client.post("/seed").json())

        print("\n--- DEMO-1 ---")
        demo1_body = client.post("/alert", json=_demo_alert_payload("DEMO-1")).json()
        incident_id = demo1_body["incident_id"]
        print(f"incident_id={incident_id}  memory_state={demo1_body['memory_state']}")
        _print_ranking("DEMO-1 ranking (before feedback)", demo1_body["ranked_fixes"])

        print(f"\n--- marking {FAILED_FIX_TYPE} as Failed on {incident_id} ---")
        fb_body = client.post(
            "/feedback",
            json={"incident_id": incident_id, "fix_type": FAILED_FIX_TYPE, "outcome": "failed", "notes": "demo_flow.py"},
        ).json()
        print(f"warnings after feedback: {[w['kind'] for w in fb_body['warnings']]}")

        print("\n--- DEMO-2 (fresh alert, same pattern) ---")
        demo2_body = client.post("/alert", json=_demo_alert_payload("DEMO-2")).json()
        print(f"incident_id={demo2_body['incident_id']}  memory_state={demo2_body['memory_state']}")
        _print_ranking("DEMO-2 ranking (after the Failed feedback)", demo2_body["ranked_fixes"])

        print("\n--- side by side ---")
        before = {f["fix_type"]: f for f in demo1_body["ranked_fixes"]}
        after = {f["fix_type"]: f for f in demo2_body["ranked_fixes"]}
        all_fix_types = sorted(set(before) | set(after), key=lambda ft: (after.get(ft) or before[ft])["rank"])
        print(f"  {'fix_type':<28} {'before score':>14} {'after score':>14}  {'before rank':>12} {'after rank':>11}")
        for ft in all_fix_types:
            b, a = before.get(ft), after.get(ft)
            b_score = f"{b['score']:+.4f}" if b else "-"
            a_score = f"{a['score']:+.4f}" if a else "-"
            print(f"  {ft:<28} {b_score:>14} {a_score:>14}  {b['rank'] if b else '-':>12} {a['rank'] if a else '-':>11}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
