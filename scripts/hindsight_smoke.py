"""Hindsight Cloud smoke test.

Creates a bank, retains one item with metadata, recalls it, runs reflect, and prints the
raw responses. Confirms the hindsight-client package works end-to-end against real config
before any app code depends on it.

Calls used (confirmed by introspecting the installed hindsight-client==0.10.1 package —
see `python -c "import inspect; from hindsight_client import Hindsight; ..."`):
  - Hindsight(base_url, api_key, timeout)
  - client.create_bank(bank_id, name, mission)
  - client.retain(bank_id, content, context, document_id, metadata)
  - client.recall(bank_id, query, max_tokens)
  - client.reflect(bank_id, query)

Usage: run from anywhere; loads .env from the repo root.
    backend/.venv/Scripts/python scripts/hindsight_smoke.py
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

import os

from hindsight_client import Hindsight

BANK_ID = "recallops-smoke-test"


def dump(label: str, obj) -> None:
    print(f"\n--- {label} ---")
    if hasattr(obj, "model_dump"):
        print(json.dumps(obj.model_dump(), indent=2, default=str))
    else:
        print(obj)


def main() -> int:
    base_url = os.environ.get("HINDSIGHT_BASE_URL")
    api_key = os.environ.get("HINDSIGHT_API_KEY")
    timeout = float(os.environ.get("HINDSIGHT_TIMEOUT", "10"))

    if not base_url or not api_key:
        print("HINDSIGHT_BASE_URL / HINDSIGHT_API_KEY missing from .env", file=sys.stderr)
        return 1

    with Hindsight(base_url=base_url, api_key=api_key, timeout=timeout) as client:
        bank = client.create_bank(
            bank_id=BANK_ID,
            name="RecallOps smoke test bank",
            mission="Scratch bank used only to verify Hindsight connectivity.",
        )
        dump("create_bank", bank)

        retained = client.retain(
            bank_id=BANK_ID,
            content=(
                "INC-SMOKE-001: payments-api SEV2. Postgres connection pool exhaustion "
                "after the v2.3.1 deploy. Increasing max pool size from 20 to 60 resolved "
                "it in 8 minutes."
            ),
            context="incident postmortem",
            document_id="INC-SMOKE-001",
            metadata={
                "incident_id": "INC-SMOKE-001",
                "service": "payments-api",
                "severity": "SEV2",
                "outcome": "worked",
            },
        )
        dump("retain", retained)

        recalled = client.recall(
            bank_id=BANK_ID,
            query="payments-api connection pool exhaustion after deploy",
            max_tokens=1024,
        )
        dump("recall", recalled)

        reflected = client.reflect(
            bank_id=BANK_ID,
            query="What fixed the payments-api connection pool exhaustion incident?",
        )
        dump("reflect", reflected)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
