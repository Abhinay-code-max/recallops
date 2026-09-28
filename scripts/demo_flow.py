"""Demo flow: reset; run DEMO-1 and print its top-3 ranked fixes with every score input;
mark increase_postgres_pool_size Worked and kill_idle_db_connections Failed on that
incident; run DEMO-2 and print the ranking again so the order change (kill_idle drops
below restart) is visible; print warnings/team_hint/recurrence for both; then, for each
alert, consume its SSE briefing stream and print time-to-first-token, total time, the
sections, and cited_incident_ids next to the recalled evidence ids -- asserting cited is
a subset of recalled (the hallucination guard, end to end).

Usage: backend/.venv/Scripts/python scripts/demo_flow.py
"""
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

DATA_DIR = REPO_ROOT / "backend" / "data"
TOP_N = 3


def _demo_alert_payload(alert_id: str) -> dict:
    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))
    demo = next(a for a in demo_alerts if a["alert_id"] == alert_id)
    return {k: demo[k] for k in ("service", "severity", "title", "symptoms", "error_message", "log_snippet", "error_signature", "submitted_at")}


def _print_ranking(label: str, ranked_fixes: list[dict]) -> None:
    print(f"\n--- {label}: top {TOP_N} ranked fixes (all score inputs) ---")
    if not ranked_fixes:
        print("  (no ranked fixes)")
        return
    for fix in ranked_fixes[:TOP_N]:
        print(
            f"  {fix['rank']}. {fix['fix_type']:<28} score={fix['score']:+.4f}  similarity={fix['similarity']:.4f}  "
            f"worked={fix['worked']} partial={fix['partial']} failed={fix['failed']} attempts={fix['attempts']} "
            f"recent_failures={fix['recent_failures']}  last_used={fix['last_used_incident_id']}"
        )


def _print_warnings_hint_recurrence(body: dict) -> None:
    print(f"  warnings: {[(w['kind'], w['message']) for w in body['warnings']]}")
    print(f"  team_hint: {body['team_hint']}")
    print(f"  recurrence: {body['recurrence']}")


def _parse_sse_block(block: str) -> tuple[str, dict]:
    lines = block.strip().splitlines()
    event = next(l.split(": ", 1)[1] for l in lines if l.startswith("event:"))
    data = json.loads(next(l.split(": ", 1)[1] for l in lines if l.startswith("data:")))
    return event, data


def _consume_briefing(client: TestClient, incident_id: str, recalled_ids: set[str]) -> None:
    url = f"/incidents/{incident_id}/briefing/stream"
    t0 = time.time()
    first_token_time = None
    events = []
    with client.stream("GET", url) as response:
        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                block, buffer = buffer.split("\n\n", 1)
                if not block.strip():
                    continue
                event, data = _parse_sse_block(block)
                if event == "token" and first_token_time is None:
                    first_token_time = time.time()
                events.append((event, data))
    total_time = time.time() - t0
    ttft = (first_token_time - t0) if first_token_time is not None else None

    sections = next(d for e, d in events if e == "sections")
    cited = set(next(d for e, d in events if e == "done")["cited_incident_ids"])

    print(f"\n--- {incident_id} briefing stream ---")
    print(f"  time_to_first_token={ttft:.3f}s" if ttft is not None else "  time_to_first_token=n/a (no token events)")
    print(f"  total_time={total_time:.3f}s")
    print(f"  sections: {json.dumps(sections, indent=2)}")
    print(f"  recalled evidence ids: {sorted(recalled_ids)}")
    print(f"  cited_incident_ids:    {sorted(cited)}")
    assert cited <= recalled_ids, f"hallucination guard violated: cited {cited - recalled_ids} not in recalled set"
    print(f"  cited subset of recalled: OK")


def main() -> int:
    with TestClient(app) as client:
        print("--- reset ---")
        print(client.post("/reset").json())

        print("\n--- seed ---")
        print(client.post("/seed").json())

        print("\n=== DEMO-1 ===")
        demo1 = client.post("/alert", json=_demo_alert_payload("DEMO-1")).json()
        incident1 = demo1["incident_id"]
        print(f"incident_id={incident1}  memory_state={demo1['memory_state']}")
        _print_ranking("DEMO-1 (before feedback)", demo1["ranked_fixes"])
        _print_warnings_hint_recurrence(demo1)

        print(f"\n--- feedback on {incident1}: increase_postgres_pool_size=Worked, kill_idle_db_connections=Failed ---")
        client.post("/feedback", json={"incident_id": incident1, "fix_type": "increase_postgres_pool_size", "outcome": "worked", "notes": "demo_flow.py"})
        fb2 = client.post("/feedback", json={"incident_id": incident1, "fix_type": "kill_idle_db_connections", "outcome": "failed", "notes": "demo_flow.py"}).json()
        print(f"warnings after feedback: {[w['kind'] for w in fb2['warnings']]}")

        print("\n=== DEMO-2 (fresh alert, same pattern) ===")
        demo2 = client.post("/alert", json=_demo_alert_payload("DEMO-2")).json()
        incident2 = demo2["incident_id"]
        print(f"incident_id={incident2}  memory_state={demo2['memory_state']}")
        _print_ranking("DEMO-2 (after the Worked/Failed feedback)", demo2["ranked_fixes"])
        _print_warnings_hint_recurrence(demo2)

        before_rank = {f["fix_type"]: f["rank"] for f in demo1["ranked_fixes"]}
        after_rank = {f["fix_type"]: f["rank"] for f in demo2["ranked_fixes"]}
        print(
            f"\norder change check: kill_idle_db_connections rank {before_rank.get('kill_idle_db_connections')} -> "
            f"{after_rank.get('kill_idle_db_connections')}, restart_payments_pods rank "
            f"{before_rank.get('restart_payments_pods')} -> {after_rank.get('restart_payments_pods')}"
        )
        if after_rank.get("kill_idle_db_connections", 0) > after_rank.get("restart_payments_pods", 999):
            print("kill_idle_db_connections now ranks below restart_payments_pods: OK")
        else:
            print("WARNING: kill_idle_db_connections did not drop below restart_payments_pods")

        print("\n=== SSE briefing streams ===")
        _consume_briefing(client, incident1, {e["incident_id"] for e in demo1["evidence"]})
        _consume_briefing(client, incident2, {e["incident_id"] for e in demo2["evidence"]})

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
