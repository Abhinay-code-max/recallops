"""Seed/reset orchestration shared by routes/seed.py, routes/reset.py and
scripts/check_recall.py, so the route and the verification script never drift apart.

Concurrency: bounded to SEED_CONCURRENCY parallel retains via asyncio.gather + a
semaphore, using the async twins on one Hindsight client instance within one event
loop -- the only combination Step A's live test confirmed doesn't crash (see
docs/HINDSIGHT_NOTES.md "## Verified behaviours" point 4).

Idempotency: every seeded retain uses update_mode="replace" with a stable document_id,
which Step A confirmed replaces (no duplicate chunks) rather than appending -- so
POST /seed can run repeatedly without growing the banks.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from app import incidents as incidents_state
from app import ledger, memory
from app.routes import briefing, insights

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
SEED_CONCURRENCY = 5


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _load_incidents() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "seed_incidents.json").read_text(encoding="utf-8"))


def _load_team() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "seed_team.json").read_text(encoding="utf-8"))


def _incident_retain_kwargs(incident: dict[str, Any]) -> dict[str, Any]:
    return dict(
        bank_id=memory.BANK_INCIDENTS,
        content=incident["text"],
        document_id=incident["document_id"],
        context=incident["title"],
        timestamp=datetime.fromisoformat(incident["timestamp"].replace("Z", "+00:00")),
        update_mode="replace",
        metadata={
            "incident_id": incident["incident_id"],
            "service": incident["service"],
            "severity": incident["severity"],
            "date": incident["timestamp"],
            "outcome": incident["fix_attempts"][-1]["outcome"],
        },
        tags=memory.seed_tags(
            incident["service"], incident["severity"], incident["incident_id"], incident.get("pattern_tags")
        ),
    )


def _fix_outcome_retain_kwargs(incident: dict[str, Any], index: int, fix: dict[str, Any]) -> dict[str, Any]:
    content = (
        f"{incident['incident_id']} ({incident['service']}, {incident['severity']}): "
        f"fix '{fix['fix_type']}' outcome={fix['outcome']} in {fix['minutes_to_effect']} min, "
        f"resolver {fix['resolver']}. {fix.get('notes', '')}"
    )
    return dict(
        bank_id=memory.BANK_FIX_OUTCOMES,
        content=content,
        document_id=f"fix-{incident['incident_id']}-{index}",
        context=f"fix attempt for {incident['incident_id']}",
        timestamp=datetime.fromisoformat(incident["timestamp"].replace("Z", "+00:00")),
        update_mode="replace",
        metadata={
            "incident_id": incident["incident_id"],
            "service": incident["service"],
            "severity": incident["severity"],
            "date": incident["timestamp"],
            "outcome": fix["outcome"],
            "fix_type": fix["fix_type"],
        },
        tags=memory.seed_tags(
            incident["service"], incident["severity"], incident["incident_id"], incident.get("pattern_tags")
        ),
    )


def _team_retain_kwargs(engineer: dict[str, Any]) -> dict[str, Any]:
    content = (
        f"{engineer['name']} ({engineer['role']}). "
        f"Specialties: {', '.join(engineer['specialties'])}. {engineer['preference']}"
    )
    return dict(
        bank_id=memory.BANK_TEAM,
        content=content,
        document_id=f"engineer-{_slug(engineer['name'])}",
        context="team profile",
        update_mode="replace",
        metadata={"name": engineer["name"]},
        tags=[f"svc:{s}" for s in engineer["specialties"]],
    )


@dataclass
class SeedResult:
    seeded: int
    failed: int
    duration_s: float


async def run_seed() -> SeedResult:
    t0 = time.time()
    await memory.ensure_banks()

    incidents = _load_incidents()
    team = _load_team()

    jobs: list[dict[str, Any]] = [_incident_retain_kwargs(inc) for inc in incidents]
    for inc in incidents:
        for i, fix in enumerate(inc["fix_attempts"]):
            jobs.append(_fix_outcome_retain_kwargs(inc, i, fix))
    jobs += [_team_retain_kwargs(eng) for eng in team]

    semaphore = asyncio.Semaphore(SEED_CONCURRENCY)

    async def _run_job(job: dict[str, Any]) -> bool:
        # Unlike memory.retain()'s general no-retry policy (safe only because most
        # callers can't guarantee idempotent targeting), every seed job here uses
        # update_mode="replace" with a stable document_id, which Step A confirmed
        # replaces rather than duplicates -- so retrying a seed job specifically is
        # provably safe, and worth doing: concurrency=5 measured ~7% of jobs timing out
        # on a single attempt.
        async with semaphore:
            for attempt in range(2):
                try:
                    await memory.retain(**job)
                    return True
                except memory.MemoryUnavailableError:
                    if attempt == 1:
                        return False
        return False

    results = await asyncio.gather(*(_run_job(job) for job in jobs))
    seeded = sum(1 for r in results if r)
    failed = sum(1 for r in results if not r)

    ledger.write_ledger(incidents)

    return SeedResult(seeded=seeded, failed=failed, duration_s=time.time() - t0)


async def run_reset() -> float:
    t0 = time.time()
    await memory.reset_live_bank()
    incidents_state.reset_live_state()
    briefing.clear_cache()
    insights.clear_cache()
    ledger.ensure_fresh()
    return time.time() - t0
