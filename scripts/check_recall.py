"""Seeds, then for each demo alert recalls the top 8 (incidents + recallops-live
merged), prints rank/incident_id/relevance with expected incidents marked '*', and
reports recall@8 per alert. Exits non-zero if any expected incident is missing from
its alert's top 8. Also prints per-bank seeded item counts, reset duration, a
leftover-smoke-bank check, and the venv python path.

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
TOP_N = 8


def _alert_query(alert: dict) -> str:
    return f"{alert['title']}. {alert['symptoms']} {alert['error_message']}"


def _augmented_query(alert: dict) -> str:
    """Query variation for item 2: append error_signature and service explicitly, in
    case the paraphrased symptoms/log wording alone doesn't carry enough of the
    matching vocabulary."""
    return f"{_alert_query(alert)} error_signature={alert['error_signature']} service={alert['service']}"


async def _recall_top(query: str):
    outcome = await memory.recall_merged([memory.BANK_INCIDENTS, memory.BANK_LIVE], query)
    return outcome, outcome.hits[:TOP_N]


def _print_ranked(top: list, expected: set[str]) -> None:
    for rank, hit in enumerate(top, start=1):
        mark = "*" if hit.incident_id in expected else " "
        relevance = f"{hit.relevance:.3f}" if hit.relevance is not None else "?"
        print(f"    {rank}. {mark} {hit.incident_id}  relevance={relevance}")


async def main() -> int:
    print(f"venv python: {sys.executable}")

    incidents = json.loads((DATA_DIR / "seed_incidents.json").read_text(encoding="utf-8"))
    team = json.loads((DATA_DIR / "seed_team.json").read_text(encoding="utf-8"))
    fix_attempts_count = sum(len(i["fix_attempts"]) for i in incidents)
    print("\n--- seeded items per bank (explains the 60) ---")
    print(f"  {memory.BANK_INCIDENTS}: {len(incidents)}")
    print(f"  {memory.BANK_FIX_OUTCOMES}: {fix_attempts_count}")
    print(f"  {memory.BANK_TEAM}: {len(team)}")
    print(f"  {memory.BANK_BASELINE}: 0 (always empty)")
    print(f"  {memory.BANK_LIVE}: 0 (nothing retains here yet -- feedback/chat/postmortem land in a later prompt)")
    print(f"  total seeded: {len(incidents) + fix_attempts_count + len(team)}")

    print("\n--- seed ---")
    seed_result = await seeding.run_seed()
    print(f"seeded={seed_result.seeded} failed={seed_result.failed} duration_s={seed_result.duration_s:.2f}")

    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))

    print("\n--- recall top 8 per demo alert (incidents + recallops-live merged) ---")
    overall_pass = True
    recall_at_8_summary: list[tuple[str, float]] = []

    for alert in demo_alerts:
        expected = set(alert["expected_incident_ids"])
        query = _alert_query(alert)
        t0 = time.time()
        outcome, top = await _recall_top(query)
        elapsed = time.time() - t0

        found = {h.incident_id for h in top} & expected
        recall_at_8 = len(found) / len(expected) if expected else 1.0
        recall_at_8_summary.append((alert["alert_id"], recall_at_8))

        print(f"\n{alert['alert_id']} ({alert['target_capability']})  query={query!r}")
        _print_ranked(top, expected)
        print(
            f"    recall@8: {len(found)}/{len(expected)} = {recall_at_8:.2f}  "
            f"latency={elapsed:.2f}s degraded={outcome.degraded}"
        )

        missing = expected - found
        if missing:
            overall_pass = False
            print(f"    MISSING from top {TOP_N}: {sorted(missing)}")
            print(f"    query used: {query!r}")

            aug_query = _augmented_query(alert)
            t0 = time.time()
            aug_outcome, aug_top = await _recall_top(aug_query)
            aug_elapsed = time.time() - t0
            aug_found = {h.incident_id for h in aug_top} & expected
            aug_recall_at_8 = len(aug_found) / len(expected) if expected else 1.0

            print(f"    variation (added error_signature + service): {aug_query!r}")
            _print_ranked(aug_top, expected)
            print(
                f"    variation recall@8: {len(aug_found)}/{len(expected)} = {aug_recall_at_8:.2f}  "
                f"latency={aug_elapsed:.2f}s degraded={aug_outcome.degraded}"
            )
            if aug_recall_at_8 > recall_at_8:
                print("    -> variation recalls better")
            elif aug_recall_at_8 < recall_at_8:
                print("    -> original recalls better")
            else:
                print("    -> no difference")

    print("\n--- recall@8 summary ---")
    for alert_id, r8 in recall_at_8_summary:
        print(f"  {alert_id}: {r8:.2f}")

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

    print(f"\n--- summary: every alert's expected incidents all landed in the top {TOP_N}: {overall_pass} ---")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
