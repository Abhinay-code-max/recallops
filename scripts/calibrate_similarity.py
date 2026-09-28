"""Prints the raw scores.final table (top 3 per query) this project's similarity
normalisation and no_match threshold are calibrated from: the 5 demo alerts (real
matches) vs 3 unrelated alerts (printer jam, marketing email bounce, HR portal login).
Asserts every normalised similarity (scoring.normalize_similarity, the exact function
scoring.py uses -- not a reimplementation) lands in [0, 1].

Usage: backend/.venv/Scripts/python scripts/calibrate_similarity.py
"""
import asyncio
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from dotenv import load_dotenv

load_dotenv(REPO_ROOT / ".env")

from app import analysis, incidents, memory, seeding  # noqa: E402
from app.scoring import normalize_similarity  # noqa: E402

DATA_DIR = REPO_ROOT / "backend" / "data"
TOP_N = 3

UNRELATED_ALERTS = [
    (
        "printer jam",
        "The office printer on the 3rd floor is jammed and printing blank pages. Someone needs to replace the toner cartridge.",
        "printer out of toner, paper jam error 0x21",
    ),
    (
        "marketing email bounce",
        "Our monthly marketing newsletter bounced for 40 subscribers due to an outdated mailing list; please clean up the CRM contacts.",
        "bounce rate 40 recipients, invalid addresses",
    ),
    (
        "HR portal login",
        "An employee can't log into the HR portal to submit a leave request; they forgot their password and need a reset link.",
        "password reset requested, HR portal SSO",
    ),
]


async def main() -> int:
    await seeding.run_seed()

    demo_alerts = json.loads((DATA_DIR / "demo_alerts.json").read_text(encoding="utf-8"))

    print(f"{'query':<34} {'rank':>4} {'incident_id':<10} {'raw scores.final':>18} {'normalised':>11}")
    print("-" * 82)

    normalized_values: list[float] = []

    for alert in demo_alerts:
        query = incidents.alert_query(alert)
        outcome = await memory.recall_merged([memory.BANK_INCIDENTS], query)
        label = alert["alert_id"]
        for rank, hit in enumerate(outcome.hits[:TOP_N], start=1):
            normalized = normalize_similarity(hit.relevance or 0.0)
            normalized_values.append(normalized)
            print(f"{label:<34} {rank:>4} {hit.incident_id:<10} {hit.relevance:>18.6f} {normalized:>11.4f}")

    print()
    for title, symptoms, error_message in UNRELATED_ALERTS:
        query = incidents.alert_query({"title": title, "symptoms": symptoms, "error_message": error_message})
        outcome = await memory.recall_merged([memory.BANK_INCIDENTS], query)
        label = title
        if not outcome.hits:
            print(f"{label:<34} {'-':>4} {'(no hits)':<10}")
            continue
        for rank, hit in enumerate(outcome.hits[:TOP_N], start=1):
            normalized = normalize_similarity(hit.relevance or 0.0)
            normalized_values.append(normalized)
            print(f"{label:<34} {rank:>4} {hit.incident_id:<10} {hit.relevance:>18.6f} {normalized:>11.4f}")

    for v in normalized_values:
        assert 0.0 <= v <= 1.0, f"normalised similarity out of [0,1]: {v}"
    print(f"\nAll {len(normalized_values)} normalised similarity values are within [0, 1]: OK")

    for title, symptoms, error_message in UNRELATED_ALERTS:
        res = await analysis.analyze_alert({"title": title, "symptoms": symptoms, "error_message": error_message})
        print(f"Unrelated alert '{title}': memory_state={res.memory_state} (threshold={analysis.NO_MATCH_THRESHOLD})")
        assert res.memory_state == "no_match", f"Expected no_match for {title}, got {res.memory_state}"
    print("All unrelated alerts evaluated to 'no_match': OK")

    await memory.get_client().aclose()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
