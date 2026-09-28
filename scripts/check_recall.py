"""Seeds, then for each demo alert recalls against incidents+recallops-live and prints
the top 3 incident IDs next to expected_incident_ids, per-call latency, seed duration,
and reset duration. Also confirms no leftover "smoke-verify-*" bank remains (Step A used
a throwaway bank of that name pattern) and prints the backend venv path.

Usage: backend/.venv/Scripts/python scripts/check_recall.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from app import memory, seeding  # noqa: E402

DATA_DIR = REPO_ROOT / "backend" / "data"


def _alert_query(alert: dict) -> str:
    return f"{alert['title']}. {alert['symptoms']} {alert['error_message']}"


async def main() -> int:
    print(f"venv python: {sys.executable}")

    print("\n--- seed ---")
    t0 = time.time()
    seed_result = await seeding.run_seed()
    seed_wall = time.time() - t0
    print(f"seeded={seed_result.seeded} failed={seed_result.failed} duration_s={seed_result.duration_s:.2f} (wall={seed_wall:.2f})")

    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))

    print("\n--- recall per demo alert (incidents + recallops-live merged) ---")
    all_ok = True
    for alert in demo_alerts:
        query = _alert_query(alert)
        t0 = time.time()
        outcome = await memory.recall_merged([memory.BANK_INCIDENTS, memory.BANK_LIVE], query)
        elapsed = time.time() - t0
        top3 = [h.incident_id for h in outcome.hits[:3]]
        expected = alert["expected_incident_ids"]
        hit_expected = bool(set(top3) & set(expected))
        all_ok = all_ok and hit_expected
        print(
            f"{alert['alert_id']} ({alert['target_capability']}): "
            f"top3={top3}  expected={expected}  "
            f"{'OK' if hit_expected else 'MISS'}  "
            f"latency={elapsed:.2f}s degraded={outcome.degraded}"
        )

    print("\n--- reset ---")
    reset_duration = await seeding.run_reset()
    print(f"reset duration_s={reset_duration:.2f}")

    print("\n--- smoke bank check ---")
    client = memory.get_client()
    listing = await client.banks.list_banks(q="smoke-verify")
    leftover = [b.bank_id for b in listing.banks]
    if leftover:
        print(f"WARNING: leftover smoke-verify bank(s) still exist: {leftover}")
    else:
        print("confirmed: no smoke-verify-* bank exists")

    await client.aclose()

    print(f"\n--- summary: all demo alerts recalled an expected incident: {all_ok} ---")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
